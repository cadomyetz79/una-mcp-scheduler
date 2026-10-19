"""Consistency of repeated runs of the same cases.

    python evaluation/variability.py --dataset heldout RUN_A RUN_B [RUN_C ...] --labels r1 r2 --out var.md

For every case present in all runs it reports, per run: pass/fail (rescored
with the dataset's current scorer), whether the run ended with an
infrastructure error, the model's tool calls and the answer. A case is
"consistent" when every completed run gives the same pass/fail. Tool-call
and answer agreement are reported separately: temperature is 0, so any
difference is run-to-run nondeterminism (CPU kernels, prompt caching), not
sampling.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.run_eval import data_dir_of, load_cases  # noqa: E402
from evaluation.scoring import score_case, score_case_v2  # noqa: E402
from scheduling.loader import load_dataset  # noqa: E402


def _calls(record: dict) -> list:
    return [(t["tool"], json.dumps(t["arguments"], sort_keys=True), t.get("by", "model"))
            for t in (record.get("result") or {}).get("trace", [])]


def analyse(data: dict, runs: list[Path]) -> list[dict]:
    v2 = data.get("scoring_version", 1) >= 2
    ds = load_dataset(data_dir_of(data))
    rows = []
    for case in data["cases"]:
        recs = []
        for run in runs:
            f = run / f"{case['id']}.json"
            recs.append(json.loads(f.read_text(encoding="utf-8"))["record"] if f.exists() else None)
        if any(r is None for r in recs):
            rows.append({"id": case["id"], "missing": [str(r) for r, x in zip(runs, recs) if x is None]})
            continue
        scores = [score_case_v2(case, r, ds) if v2 else score_case(case, r) for r in recs]
        infra = [("error" in r) for r in recs]
        done = [s["pass"] for s, bad in zip(scores, infra) if not bad]
        answers = [(r.get("result") or {}).get("answer") for r in recs]
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "pass": [s["pass"] for s in scores],
            "infrastructure_error": infra,
            "consistent": len(set(done)) <= 1 if done else None,
            "same_tool_calls": len({json.dumps(_calls(r)) for r in recs}) == 1,
            "same_answer": len(set(answers)) == 1,
            "failed_checks": [[k for k, c in s["checks"].items() if not c["pass"]] for s in scores],
            "wall_s": [r.get("wall_s") for r in recs],
        })
    return rows


def to_markdown(rows: list[dict], labels: list[str]) -> str:
    done = [r for r in rows if "missing" not in r]
    both = [r for r in done if not any(r["infrastructure_error"])]
    lines = [
        f"# Repeated runs: {', '.join(labels)}",
        "",
        f"- Cases in all runs: {len(done)}; missing in some run: {[r['id'] for r in rows if 'missing' in r] or 'none'}",
        f"- Cases completed without infrastructure error in every run: {len(both)}",
        f"- Same pass/fail in every completed run: {sum(1 for r in done if r['consistent'])}/"
        f"{sum(1 for r in done if r['consistent'] is not None)}",
        f"- Pass/fail changed between runs: {[r['id'] for r in done if r['consistent'] is False]}",
        f"- Identical tool calls in every run: {sum(r['same_tool_calls'] for r in both)}/{len(both)} "
        f"(cases without infrastructure errors)",
        f"- Identical final answer in every run: {sum(r['same_answer'] for r in both)}/{len(both)}",
    ]
    for i, label in enumerate(labels):
        lines.append(f"- {label}: passed {sum(r['pass'][i] for r in done)}/{len(done)}, "
                     f"infrastructure errors {sum(r['infrastructure_error'][i] for r in done)}")
    lines += ["", "| Case | Category | " + " | ".join(labels) + " | Consistent | Same calls | Same answer |",
              "|---|---|" + "---|" * len(labels) + "---|---|---|"]
    for r in rows:
        if "missing" in r:
            lines.append(f"| {r['id']} | missing | " + " | " * len(labels) + " | | |")
            continue
        cells = []
        for ok, bad, failed in zip(r["pass"], r["infrastructure_error"], r["failed_checks"]):
            cells.append("infra" if bad else ("pass" if ok else "FAIL: " + ", ".join(failed)))
        lines.append(f"| {r['id']} | {r['category']} | " + " | ".join(cells)
                     + f" | {r['consistent']} | {r['same_tool_calls']} | {r['same_answer']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("runs", nargs="+")
    p.add_argument("--dataset", default="heldout")
    p.add_argument("--labels", nargs="+")
    p.add_argument("--out")
    a = p.parse_args()
    labels = a.labels or [f"run{i + 1}" for i in range(len(a.runs))]
    rows = analyse(load_cases(dataset=a.dataset), [Path(r) for r in a.runs])
    md = to_markdown(rows, labels)
    print(md)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
