"""Run the evaluation cases through the real assistant and score them.

    # live model (Ollama must be running with the model pulled)
    python evaluation/run_eval.py --model qwen3:8b --no-think --out ../docs/evidence/eval-run

    # oracle: replay each case's ideal tool calls (no model) to check the dataset
    python evaluation/run_eval.py --oracle --out /tmp/eval-oracle

    # subset
    python evaluation/run_eval.py --cases E01 E02 --model qwen3:8b

The assistant, planner and MCP server are the real ones (fake MCP server
over stdio, the same path as dev/chat.py). Each case gets a fresh MCP session
and assistant, bound to the case's student_id. Per-case records are written
as soon as each case finishes, so a long run keeps its partial results.
Outputs in --out: E01.json ... (run + score), summary.json, summary.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from agent.assistant import INTERNAL_MESSAGES, PROMPT_PATH, TOOL_SPECS, SchedulingAssistant  # noqa: E402
from agent.banner_tools import BannerTools  # noqa: E402
from agent.llm import LLMError, OllamaLLM, ScriptedLLM  # noqa: E402
from agent.security import LeakGuard, protected_texts, redact_for_log  # noqa: E402
from evaluation.scoring import score_case, score_case_v2, summarize, summarize_v2  # noqa: E402
from scheduling.loader import load_dataset  # noqa: E402

CASES_PATH = Path(__file__).resolve().with_name("cases.json")
DATASETS = {
    "dev": CASES_PATH,  # development set (19 cases); its v1 results are historical evidence
    # held-out set (34 cases): development data since the security-hardening work
    "heldout": Path(__file__).resolve().parent / "heldout" / "cases.json",
    "security": Path(__file__).resolve().parent / "security" / "live_cases.json",  # development data
    # second held-out set, pre-registered for future generalisation claims (heldout2/README.md)
    "heldout2": Path(__file__).resolve().parent / "heldout2" / "cases.json",
}
DEV_V2_OVERLAY = Path(__file__).resolve().with_name("dev_scoring_v2.json")
SERVER = ROOT / "dev" / "fake_mcp_server.py"


def data_dir_of(data: dict) -> Path:
    return (ROOT / data["data_dir"]).resolve() if data.get("data_dir") else (ROOT.parent / "data").resolve()


def load_cases(ids: list[str] | None = None, dataset: str = "dev", scoring_version: int | None = None) -> dict:
    data = json.loads(DATASETS[dataset].read_text(encoding="utf-8"))
    data.setdefault("scoring_version", 1)
    if scoring_version:
        data["scoring_version"] = scoring_version
    if dataset == "dev" and data["scoring_version"] >= 2:
        # v2 adds stricter assertions to some development cases (documented in the overlay).
        overlay = json.loads(DEV_V2_OVERLAY.read_text(encoding="utf-8"))
        for c in data["cases"]:
            c["expect"] = {**c["expect"], **overlay["expect"].get(c["id"], {})}
            c["oracle"] = overlay.get("oracle", {}).get(c["id"], c["oracle"])
    if ids:
        data["cases"] = [c for c in data["cases"] if c["id"] in ids]
    return data


async def run_case(case: dict, term_id: str, llm, server_params,
                   check_preference_language: bool = True, check_evidence: bool = True,
                   check_security: bool = True) -> dict:
    record = {"case_id": case["id"], "request": case["request"], "student_id": case["student_id"],
              "term_id": term_id}
    started = time.perf_counter()
    try:
        async with Client(server_params) as client:
            assistant = SchedulingAssistant(BannerTools(client), llm, case["student_id"], term_id,
                                            check_preference_language=check_preference_language,
                                            check_evidence=check_evidence,
                                            check_security=check_security)
            result = await assistant.run(case["request"])
        record["result"] = result.to_dict()
    except (LLMError, Exception) as e:  # keep going: a failed case is evidence too
        record["error"] = f"{type(e).__name__}: {e}"
        # anyio wraps the real cause in an ExceptionGroup; keep the leaves too.
        leaves, stack = [], [e]
        while stack:
            x = stack.pop()
            subs = getattr(x, "exceptions", None)
            if subs:
                stack.extend(subs)
            else:
                leaves.append(f"{type(x).__name__}: {x}")
        record["error_causes"] = leaves
        record["error_kind"] = classify_error(" ".join(leaves))
    record["wall_s"] = round(time.perf_counter() - started, 2)
    if isinstance(llm, OllamaLLM):
        record["llm_calls"] = llm.stats[:]
        llm.stats.clear()
    return record


def redact_record(record: dict, term_id: str) -> dict:
    """Evaluation records never keep internal instructions or data verbatim.

    With the security layer on, a leaking answer is already replaced; this also
    covers ablation runs (--no-security-check), where it would be returned.
    The scorer runs before redaction, on the real answer."""
    answer = (record.get("result") or {}).get("answer")
    if answer:
        guard = LeakGuard(protected_texts(
            PROMPT_PATH.read_text(encoding="utf-8").replace("{term_id}", term_id), TOOL_SPECS, INTERNAL_MESSAGES))
        logged = redact_for_log(answer, guard)
        if logged != answer:
            record["result"]["answer"] = logged
            record["answer_redacted_in_log"] = True
    return record


def classify_error(text: str) -> str:
    """Infrastructure vs. other failures, from the error text only (not from scores)."""
    t = text.lower()
    if "timed out" in t or "timeout" in t:
        return "infrastructure:timeout"
    if "ollama returned 5" in t or "llama-server process has terminated" in t or "cannot reach ollama" in t:
        return "infrastructure:model_server"
    return "other"


def write_markdown(path: Path, meta: dict, summary: dict, scores: list[dict], records: list[dict]) -> None:
    by_id = {r["case_id"]: r for r in records}
    lines = [
        f"# Evaluation run — {meta['started_utc']}",
        "",
        f"- Mode: {meta['mode']}; model: {meta.get('model')}; think: {meta.get('think')}; "
        f"num_ctx: {meta.get('num_ctx')}",
        f"- Machine: {meta['machine']}",
        f"- Preference check: {meta.get('preference_check')}; evidence check: {meta.get('evidence_check')}; "
        f"security checks: {meta.get('security_check', 'n/a (before 2026-10-19 security work)')}; "
        f"num_predict: {meta.get('num_predict')}",
        f"- Cases passed: {summary['cases']['passed']}/{summary['cases']['total']}"
        f" (missing: {', '.join(summary.get('cases_missing', [])) or 'none'})",
        f"- Preference classification: model {summary['preference_classification']['model_raw']['passed']}/"
        f"{summary['preference_classification']['model_raw']['total']}, applied "
        f"{summary['preference_classification']['applied']['passed']}/"
        f"{summary['preference_classification']['applied']['total']}",
        f"- Tool-call correctness: {summary['tool_call_correctness']['passed']}/"
        f"{summary['tool_call_correctness']['total']}; invalid tool calls: {summary['invalid_tool_calls']}",
        f"- Grounded answers: {summary['grounded']['passed']}/{summary['grounded']['total']}",
        f"- Hard-constraint violations in returned options: {summary['hard_constraint_violations']['count']}",
        f"- Model made the right plan call itself: {summary['model_plan_correct']['passed']}/"
        f"{summary['model_plan_correct']['total']}",
        f"- Evidence recoveries: {summary['recoveries']['nudges']} nudges, "
        f"{summary['recoveries']['system_plan_schedule']} system-run plans, "
        f"{summary['recoveries']['not_run']} not run; cases: {summary['recoveries']['cases_with_recovery'] or 'none'}",
        f"- Unsupported availability/eligibility claims in final answers (audit): "
        f"{summary['unsupported_claims']['audit_in_final_answers']} {summary['unsupported_claims']['audit_cases']}",
        f"- Latency (s): median {summary['latency_s']['median']}, mean {summary['latency_s']['mean']}, "
        f"max {summary['latency_s']['max']}",
        "",
        "| Criterion | Passed | Rate |",
        "|---|---|---|",
    ]
    for name, r in summary["criteria"].items():
        lines.append(f"| {name} | {r['passed']}/{r['total']} | {r['rate']} |")
    if "false_claims" in summary:
        lines[7:7] = [
            f"- Scoring version: {summary.get('scoring_version')}",
            f"- False academic claims (vs. dataset truth): {summary['false_claims']['count']} "
            f"{summary['false_claims']['cases']}",
            f"- Claims without plan_schedule support (v2 audit): {summary['unsupported_claims_v2']['count']} "
            f"{summary['unsupported_claims_v2']['cases']}",
            f"- Tokens: prompt {summary['tokens']['prompt']}, output {summary['tokens']['output']}",
        ]
    lines += ["", "| Case | Pass | Failed checks | Tools | Wall s |", "|---|---|---|---|---|"]
    for s in scores:
        r = by_id[s["id"]]
        failed = ", ".join(k for k, c in s["checks"].items() if not c["pass"]) or "-"
        tools = ", ".join(t["tool"] for t in (r.get("result") or {}).get("trace", [])) or "-"
        lines.append(f"| {s['id']} | {'yes' if s['pass'] else 'no'} | {failed} | {tools} | {r.get('wall_s')} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", nargs="*", help="case IDs to run (default: all)")
    p.add_argument("--dataset", choices=sorted(DATASETS), default="dev")
    p.add_argument("--scoring-version", type=int, choices=[1, 2],
                   help="default: the dataset's own (dev 1, heldout 2)")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--no-think", action="store_true")
    p.add_argument("--num-ctx", type=int)
    p.add_argument("--timeout", type=float, default=300,
                   help="seconds per model call before the client gives up (OllamaLLM default 300)")
    p.add_argument("--oracle", action="store_true", help="replay each case's ideal responses, no model")
    p.add_argument("--no-preference-check", action="store_true",
                   help="ablation: let the model's required_preferences stand unchecked")
    p.add_argument("--no-evidence-check", action="store_true",
                   help="ablation: no evidence orchestration / claim check (agent/evidence.py)")
    p.add_argument("--no-security-check", action="store_true",
                   help="ablation: no input inspection / output guard (agent/security.py); unverified "
                        "answers are returned flagged as before 2026-10-19")
    p.add_argument("--num-predict", type=int,
                   help="cap on output tokens per model call (default: no cap)")
    p.add_argument("--resume", action="store_true",
                   help="keep finished cases already in --out and run only the missing ones")
    p.add_argument("--summarize-only", action="store_true",
                   help="rebuild summary.json/.md from the case files in --out, no runs")
    p.add_argument("--out", required=True)
    a = p.parse_args()

    data = load_cases(a.cases, a.dataset, a.scoring_version)
    v2 = data["scoring_version"] >= 2
    ds = load_dataset(data_dir_of(data))

    def rescore(case, record):
        return score_case_v2(case, record, ds) if v2 else score_case(case, record)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "oracle" if a.oracle else "live",
        "model": None if a.oracle else a.model,
        "think": None if a.oracle else (not a.no_think),
        "num_ctx": a.num_ctx,
        "llm_timeout_s": a.timeout,
        "preference_check": not a.no_preference_check,
        "evidence_check": not a.no_evidence_check,
        "security_check": not a.no_security_check,
        "num_predict": a.num_predict,
        "cases_version": data["version"],
        "dataset": a.dataset,
        "data_dir": str(data_dir_of(data).relative_to(ROOT.parent)),
        "scoring_version": data["scoring_version"],
        "machine": f"{platform.system()} {platform.machine()} python {platform.python_version()}",
    }
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)],
                                   env={**os.environ, "UNA_DATA_DIR": str(data_dir_of(data))})
    live_llm = None if a.oracle else OllamaLLM(model=a.model, think=False if a.no_think else None,
                                               num_ctx=a.num_ctx, timeout=a.timeout,
                                               num_predict=a.num_predict)

    records, scores = [], []
    saved_meta = None
    for case in data["cases"]:
        path = out / f"{case['id']}.json"
        if (a.resume or a.summarize_only) and path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved_meta = saved_meta or saved.get("meta")
            record = saved["record"]
            score = rescore(case, record)  # rescored with the current scorer
            records.append(record)
            scores.append(score)
            print(f"{case['id']} kept from earlier run pass={score['pass']}", flush=True)
            continue
        if a.summarize_only:
            print(f"{case['id']} missing (not run)", flush=True)
            continue
        llm = ScriptedLLM(case["oracle"]) if a.oracle else live_llm
        record = await run_case(case, data["term_id"], llm, params,
                                check_preference_language=not a.no_preference_check,
                                check_evidence=not a.no_evidence_check,
                                check_security=not a.no_security_check)
        score = rescore(case, record)
        record = redact_record(record, data["term_id"])
        records.append(record)
        scores.append(score)
        path.write_text(
            json.dumps({"meta": meta, "record": record, "score": score}, indent=2), encoding="utf-8")
        failed = [k for k, c in score["checks"].items() if not c["pass"]]
        print(f"{case['id']} pass={score['pass']} wall={record['wall_s']}s failed={failed}", flush=True)

    if a.summarize_only and saved_meta:
        # Keep the settings of the run that produced the records; note the rescoring.
        meta = {**saved_meta, "rescored_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rescored_with": f"current evaluation/scoring.py, scoring v{data['scoring_version']}",
                "scoring_version": data["scoring_version"]}
        meta.setdefault("preference_check", not a.no_preference_check)
        meta.setdefault("evidence_check", not a.no_evidence_check)
    summary = (summarize_v2(data["cases"], scores, records, ds) if v2
               else summarize(data["cases"], scores, records, ds))
    summary["cases_missing"] = [c["id"] for c in data["cases"]
                                if c["id"] not in {r["case_id"] for r in records}]
    if not a.summarize_only:
        meta["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2),
                                      encoding="utf-8")
    write_markdown(out / "summary.md", meta, summary, scores, records)
    print(json.dumps(summary["cases"]), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
