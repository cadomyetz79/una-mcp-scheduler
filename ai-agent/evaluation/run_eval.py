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
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from agent.assistant import SchedulingAssistant  # noqa: E402
from agent.banner_tools import BannerTools  # noqa: E402
from agent.llm import LLMError, OllamaLLM, ScriptedLLM  # noqa: E402
from evaluation.scoring import score_case, summarize  # noqa: E402

CASES_PATH = Path(__file__).resolve().with_name("cases.json")
SERVER = ROOT / "dev" / "fake_mcp_server.py"


def load_cases(ids: list[str] | None = None) -> dict:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if ids:
        data["cases"] = [c for c in data["cases"] if c["id"] in ids]
    return data


async def run_case(case: dict, term_id: str, llm, server_params) -> dict:
    record = {"case_id": case["id"], "request": case["request"], "student_id": case["student_id"],
              "term_id": term_id}
    started = time.perf_counter()
    try:
        async with Client(server_params) as client:
            assistant = SchedulingAssistant(BannerTools(client), llm, case["student_id"], term_id)
            result = await assistant.run(case["request"])
        record["result"] = result.to_dict()
    except (LLMError, Exception) as e:  # keep going: a failed case is evidence too
        record["error"] = f"{type(e).__name__}: {e}"
    record["wall_s"] = round(time.perf_counter() - started, 2)
    if isinstance(llm, OllamaLLM):
        record["llm_calls"] = llm.stats[:]
        llm.stats.clear()
    return record


def write_markdown(path: Path, meta: dict, summary: dict, scores: list[dict], records: list[dict]) -> None:
    by_id = {r["case_id"]: r for r in records}
    lines = [
        f"# Evaluation run — {meta['started_utc']}",
        "",
        f"- Mode: {meta['mode']}; model: {meta.get('model')}; think: {meta.get('think')}; "
        f"num_ctx: {meta.get('num_ctx')}",
        f"- Machine: {meta['machine']}",
        f"- Cases passed: {summary['cases']['passed']}/{summary['cases']['total']}",
        f"- Latency (s): median {summary['latency_s']['median']}, mean {summary['latency_s']['mean']}, "
        f"max {summary['latency_s']['max']}",
        "",
        "| Criterion | Passed | Rate |",
        "|---|---|---|",
    ]
    for name, r in summary["criteria"].items():
        lines.append(f"| {name} | {r['passed']}/{r['total']} | {r['rate']} |")
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
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--no-think", action="store_true")
    p.add_argument("--num-ctx", type=int)
    p.add_argument("--oracle", action="store_true", help="replay each case's ideal responses, no model")
    p.add_argument("--out", required=True)
    a = p.parse_args()

    data = load_cases(a.cases)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "oracle" if a.oracle else "live",
        "model": None if a.oracle else a.model,
        "think": None if a.oracle else (not a.no_think),
        "num_ctx": a.num_ctx,
        "cases_version": data["version"],
        "machine": f"{platform.system()} {platform.machine()} python {platform.python_version()}",
    }
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    live_llm = None if a.oracle else OllamaLLM(model=a.model, think=False if a.no_think else None,
                                               num_ctx=a.num_ctx)

    records, scores = [], []
    for case in data["cases"]:
        llm = ScriptedLLM(case["oracle"]) if a.oracle else live_llm
        record = await run_case(case, data["term_id"], llm, params)
        score = score_case(case, record)
        records.append(record)
        scores.append(score)
        (out / f"{case['id']}.json").write_text(
            json.dumps({"meta": meta, "record": record, "score": score}, indent=2), encoding="utf-8")
        failed = [k for k, c in score["checks"].items() if not c["pass"]]
        print(f"{case['id']} pass={score['pass']} wall={record['wall_s']}s failed={failed}", flush=True)

    summary = summarize(data["cases"], scores, records)
    meta["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2),
                                      encoding="utf-8")
    write_markdown(out / "summary.md", meta, summary, scores, records)
    print(json.dumps(summary["cases"]), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
