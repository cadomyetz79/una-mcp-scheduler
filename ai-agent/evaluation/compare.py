"""Compare two evaluation runs case by case (e.g. baseline vs. preference check).

    python evaluation/compare.py RUN_A RUN_B --labels baseline check --out comparison.md

Both runs are rescored with the current scorer from their saved case files.
For every case it reports whether the MODEL's own tool calls were the same
in both runs. That separates two causes of a different result:
  - same model calls, different outcome  -> caused by the system change
  - different model calls                -> the model behaved differently
                                             (variance), not the change alone
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.run_eval import load_cases  # noqa: E402
from evaluation.scoring import score_case  # noqa: E402


def _calls(record: dict) -> list:
    return [(t["tool"], json.dumps(t["arguments"], sort_keys=True))
            for t in (record.get("result") or {}).get("trace", [])]


def load_run(path: Path, cases: list[dict]) -> dict:
    run = {}
    for case in cases:
        f = path / f"{case['id']}.json"
        if f.exists():
            record = json.loads(f.read_text(encoding="utf-8"))["record"]
            run[case["id"]] = {"record": record, "score": score_case(case, record)}
    return run


def compare(cases: list[dict], a: dict, b: dict) -> list[dict]:
    rows = []
    for case in cases:
        cid = case["id"]
        if cid not in a or cid not in b:
            rows.append({"id": cid, "missing": [n for n, r in (("A", a), ("B", b)) if cid not in r]})
            continue
        sa, sb = a[cid]["score"], b[cid]["score"]
        ra, rb = a[cid]["record"], b[cid]["record"]
        same_calls = _calls(ra) == _calls(rb)
        if sa["pass"] == sb["pass"]:
            change = "same"
        elif sb["pass"]:
            change = "fixed"
        else:
            change = "new_error"
        rows.append({
            "id": cid,
            "category": case["category"],
            "pass": [sa["pass"], sb["pass"]],
            "change": change,
            "cause": "system" if same_calls else "model_variance",
            "failed": [[k for k, c in s["checks"].items() if not c["pass"]] for s in (sa, sb)],
            "model_required_correct": [s.get("extra", {}).get("model_required_correct") for s in (sa, sb)],
            "corrections": sb.get("extra", {}).get("corrections", []),
            "wall_s": [ra.get("wall_s"), rb.get("wall_s")],
            "tools": [[t for t, _ in _calls(r)] for r in (ra, rb)],
        })
    return rows


def to_markdown(rows: list[dict], labels: list[str]) -> str:
    A, B = labels
    done = [r for r in rows if "missing" not in r]
    lines = [
        f"# Comparison: {A} vs {B}",
        "",
        f"- Cases compared: {len(done)}; missing: {[r['id'] for r in rows if 'missing' in r] or 'none'}",
        f"- Passed: {A} {sum(r['pass'][0] for r in done)}/{len(done)}, "
        f"{B} {sum(r['pass'][1] for r in done)}/{len(done)}",
        f"- Fixed in {B}: {[r['id'] for r in done if r['change'] == 'fixed']}",
        f"- New errors in {B}: {[r['id'] for r in done if r['change'] == 'new_error']}",
        f"- Cases where the model's own tool calls differed between runs: "
        f"{[r['id'] for r in done if r['cause'] == 'model_variance']}",
        "",
        f"| Case | Category | {A} | {B} | Change | Cause | Failed checks ({A} / {B}) | Corrections in {B} | Wall s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "missing" in r:
            lines.append(f"| {r['id']} | | | | missing in {r['missing']} | | | | |")
            continue
        fixes = "; ".join(f"{c['preference']}: {c['model_said']}->{c['applied']}" for c in r["corrections"]) or "-"
        failed = " / ".join(", ".join(f) or "-" for f in r["failed"])
        lines.append(
            f"| {r['id']} | {r['category']} | {'pass' if r['pass'][0] else 'FAIL'} | "
            f"{'pass' if r['pass'][1] else 'FAIL'} | {r['change']} | {r['cause']} | {failed} | {fixes} | "
            f"{r['wall_s'][0]} / {r['wall_s'][1]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run_a")
    p.add_argument("run_b")
    p.add_argument("--labels", nargs=2, default=["A", "B"])
    p.add_argument("--out", help="write markdown here (and .json next to it)")
    a = p.parse_args()
    cases = load_cases()["cases"]
    rows = compare(cases, load_run(Path(a.run_a), cases), load_run(Path(a.run_b), cases))
    md = to_markdown(rows, a.labels)
    print(md)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
