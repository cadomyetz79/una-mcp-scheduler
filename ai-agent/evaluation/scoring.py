"""Deterministic scoring of one assistant run against one evaluation case.

Input is the saved run record (the same shape dev/chat.py --save writes):
    {"student_id": ..., "result": AssistantResult.to_dict(), ...}
Nothing here calls a model; scores depend only on the recorded trace, so
they can be recomputed later from the evidence files.

Criteria (a case only gets the ones its "expect" block asks for):
    tool_use        must_call tools were called (successfully), must_not_call were not
    course_ids      last successful plan_schedule call used exactly these course IDs
    preferences     its earliest_start / latest_end / avoid_days match exactly
    required        its required_preferences match exactly (mandatory vs. soft)
    outcome         its options (as section sets) and excluded codes match
    grounded        assistant reported grounded=True (always scored)
    privacy         no MCP call used another student's ID (always scored)
    answer          answer_any groups found and answer_none phrases absent
    completed       loop ended with an answer, not the step limit (always scored)
"""

from __future__ import annotations

PREF_KEYS = ("earliest_start", "latest_end", "avoid_days")


def _norm_prefs(args: dict) -> dict:
    out = {}
    for key in PREF_KEYS:
        value = args.get(key)
        if value in (None, "", []):
            continue
        out[key] = sorted(str(d).upper() for d in value) if key == "avoid_days" else str(value)
    return out


def _last_plan(trace: list[dict]) -> dict | None:
    plans = [t for t in trace if t["tool"] == "plan_schedule" and t["ok"]]
    return plans[-1] if plans else None


def score_case(case: dict, record: dict) -> dict:
    expect = case.get("expect", {})
    result = record.get("result") or {}
    trace = result.get("trace", [])
    checks: dict[str, dict] = {}

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks[name] = {"pass": bool(passed), "detail": detail}

    if "error" in record:
        check("completed", False, f"run error: {record['error']}")
        return {"id": case["id"], "pass": False, "checks": checks}

    called_ok = {t["tool"] for t in trace if t["ok"]}
    called_any = {t["tool"] for t in trace}
    if "must_call" in expect or "must_not_call" in expect:
        missing = [t for t in expect.get("must_call", []) if t not in called_ok]
        forbidden = [t for t in expect.get("must_not_call", []) if t in called_any]
        check("tool_use", not missing and not forbidden,
              f"missing={missing} forbidden={forbidden} called={sorted(called_any)}")

    plan = _last_plan(trace)
    plan_args = plan["arguments"] if plan else {}
    plan_result = plan["result"] if plan else {}

    if "plan_course_ids" in expect:
        got = sorted(str(c).strip().upper() for c in plan_args.get("course_ids", []))
        want = sorted(expect["plan_course_ids"])
        check("course_ids", plan is not None and got == want, f"got={got} want={want}")

    if "preferences" in expect:
        got = _norm_prefs(plan_args)
        want = _norm_prefs(expect["preferences"])
        check("preferences", plan is not None and got == want, f"got={got} want={want}")

    if "required_preferences" in expect:
        got = sorted(plan_args.get("required_preferences") or [])
        want = sorted(expect["required_preferences"])
        check("required", plan is not None and got == want, f"got={got} want={want}")

    if "options" in expect or "excluded" in expect:
        got_opts = sorted(sorted(o["section_ids"]) for o in plan_result.get("options", []))
        want_opts = sorted(sorted(o) for o in expect.get("options", got_opts))
        got_exc = {e["course_id"]: e["code"] for e in plan_result.get("excluded", [])}
        want_exc = expect.get("excluded", got_exc)
        check("outcome", plan is not None and got_opts == want_opts and got_exc == want_exc,
              f"options={got_opts} want={want_opts} excluded={got_exc} want={want_exc}")

    check("grounded", bool(result.get("grounded")),
          f"ungrounded={result.get('ungrounded_section_ids', [])}")

    bound = record.get("student_id")
    foreign = [c for c in result.get("mcp_calls", [])
               if c.get("arguments", {}).get("student_id") not in (None, bound)]
    check("privacy", not foreign, f"foreign_calls={foreign}")

    if "answer_any" in expect or "answer_none" in expect:
        text = (result.get("answer") or "").lower()
        missing_groups = [g for g in expect.get("answer_any", [])
                          if not any(p.lower() in text for p in g)]
        present = [p for p in expect.get("answer_none", []) if p.lower() in text]
        check("answer", not missing_groups and not present,
              f"missing_groups={missing_groups} forbidden_present={present}")

    check("completed", result.get("stopped_reason") == "answered",
          f"stopped_reason={result.get('stopped_reason')}")

    return {"id": case["id"], "pass": all(c["pass"] for c in checks.values()), "checks": checks}


def summarize(cases: list[dict], scores: list[dict], records: list[dict]) -> dict:
    by_id = {c["id"]: c for c in cases}
    criteria: dict[str, list[bool]] = {}
    for s in scores:
        for name, c in s["checks"].items():
            criteria.setdefault(name, []).append(c["pass"])
    walls = sorted(r["wall_s"] for r in records if "wall_s" in r and "error" not in r)
    categories: dict[str, list[bool]] = {}
    for s in scores:
        categories.setdefault(by_id[s["id"]]["category"], []).append(s["pass"])

    def rate(values: list[bool]) -> dict:
        return {"passed": sum(values), "total": len(values),
                "rate": round(sum(values) / len(values), 3) if values else None}

    return {
        "cases": rate([s["pass"] for s in scores]),
        "criteria": {k: rate(v) for k, v in sorted(criteria.items())},
        "categories": {k: rate(v) for k, v in sorted(categories.items())},
        "latency_s": {
            "n": len(walls),
            "median": walls[len(walls) // 2] if walls else None,
            "mean": round(sum(walls) / len(walls), 2) if walls else None,
            "max": walls[-1] if walls else None,
        },
        "model_calls_total": sum((r.get("result") or {}).get("model_calls", 0) for r in records),
        "errors": [r["case_id"] for r in records if "error" in r],
    }
