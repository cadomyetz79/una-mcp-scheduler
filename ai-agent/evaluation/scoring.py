"""Deterministic scoring of one assistant run against one evaluation case.

Input is the saved run record (the same shape dev/chat.py --save writes):
    {"student_id": ..., "result": AssistantResult.to_dict(), ...}
Nothing here calls a model; scores depend only on the recorded trace, so
they can be recomputed later from the evidence files.

Criteria (a case only gets the ones its "expect" block asks for):
    tool_use        must_call tools were called (successfully), must_not_call were not
    course_ids      last successful plan_schedule call used exactly these course IDs
    preferences     its earliest_start / latest_end / avoid_days match exactly
    required        the mandatory set actually APPLIED matches (after the assistant's
                    preference check, if it ran; the model's raw choice is
                    reported separately as preference_classification)
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

    extra: dict = {}
    if "required_preferences" in expect:
        raw = sorted(plan_args.get("required_preferences") or [])
        applied = sorted((plan_result.get("preferences_applied") or {}).get("required", raw))
        want = sorted(expect["required_preferences"])
        check("required", plan is not None and applied == want,
              f"applied={applied} model={raw} want={want}")
        extra["model_required_correct"] = plan is not None and raw == want
        extra["corrections"] = plan_result.get("preference_corrections", [])

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

    extra["invalid_tool_calls"] = sum(1 for t in trace if not t["ok"])
    # Evidence orchestration (absent in runs made before it existed).
    extra["recoveries"] = [r["type"] for r in result.get("recoveries", [])]
    extra["system_tool_calls"] = sum(1 for t in trace if t.get("by") == "system")
    extra["runtime_unsupported_claims"] = len(result.get("unsupported_claims", []))
    extra["rejected_section_mentions"] = result.get("rejected_section_mentions", [])
    # Same claim rule applied offline to the final answer, so runs made before
    # the runtime check existed can be compared on equal terms.
    from agent.evidence import unsupported_claims
    extra["audit_unsupported_claims"] = unsupported_claims(result.get("answer") or "", trace)
    # Did the MODEL itself make the right plan call (ignoring system-run calls)?
    if "plan_course_ids" in expect:
        model_plans = [t for t in trace if t["tool"] == "plan_schedule" and t["ok"] and t.get("by", "model") == "model"]
        got = sorted(str(c).strip().upper() for c in (model_plans[-1]["arguments"].get("course_ids", [])
                                                         if model_plans else []))
        extra["model_plan_correct"] = bool(model_plans) and got == sorted(expect["plan_course_ids"])
    return {"id": case["id"], "pass": all(c["pass"] for c in checks.values()), "checks": checks,
            "extra": extra}


def hard_constraint_violations(record: dict, ds) -> list[dict]:
    """Re-check every option the planner returned in this run against the
    deterministic validator and the mandatory preferences that were applied.
    By design this should always be empty; the evaluation measures it anyway."""
    from agent.planner import Preferences
    from scheduling.validators import validate_schedule

    found = []
    student = ds.students.get(record.get("student_id"))
    for t in (record.get("result") or {}).get("trace", []):
        if t["tool"] != "plan_schedule" or not t["ok"]:
            continue
        # Runs made before the preference check existed have no
        # preferences_applied; then the model's arguments were what was applied.
        applied = t["result"].get("preferences_applied")
        if applied is None:
            args = t["arguments"]
            applied = {**args, "required": args.get("required_preferences") or []}
        prefs = Preferences(applied.get("earliest_start") or None, applied.get("latest_end") or None,
                            tuple(d.upper() for d in applied.get("avoid_days") or ()),
                            tuple(applied.get("required") or ()))
        for option in t["result"].get("options", []):
            ids = option["section_ids"]
            check = validate_schedule(student, ids, record.get("term_id"), ds.sections, ds.courses)
            broken = [s for s in ids if s in ds.sections and not prefs.allows(ds.sections[s])]
            if not check.valid or broken:
                found.append({"section_ids": ids, "issues": [i.code for i in check.issues],
                              "required_preference_broken_by": broken})
    return found


def summarize(cases: list[dict], scores: list[dict], records: list[dict], ds=None) -> dict:
    by_id = {c["id"]: c for c in cases}
    rec_by_id = {r["case_id"]: r for r in records}
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

    pref_scores = [s for s in scores if "model_required_correct" in s.get("extra", {})]
    tool_correct = []
    for s in scores:
        relevant = [s["checks"][k]["pass"] for k in ("tool_use", "course_ids", "preferences")
                    if k in s["checks"]]
        if relevant:
            tool_correct.append(all(relevant))
    violations = {}
    if ds is not None:
        for s in scores:
            v = hard_constraint_violations(rec_by_id[s["id"]], ds)
            if v:
                violations[s["id"]] = v
    per_case_latency = {s["id"]: rec_by_id[s["id"]].get("wall_s") for s in scores}
    ex = [s.get("extra", {}) for s in scores]
    recov = [k for e in ex for k in e.get("recoveries", [])]
    plan_cases = [e for e in ex if "model_plan_correct" in e]

    return {
        "cases": rate([s["pass"] for s in scores]),
        "preference_classification": {
            "model_raw": rate([s["extra"]["model_required_correct"] for s in pref_scores]),
            "applied": rate([s["checks"]["required"]["pass"] for s in pref_scores]),
            "corrections": {s["id"]: s["extra"]["corrections"] for s in pref_scores
                            if s["extra"]["corrections"]},
        },
        "tool_call_correctness": rate(tool_correct),
        "grounded": rate([s["checks"]["grounded"]["pass"] for s in scores if "grounded" in s["checks"]]),
        "invalid_tool_calls": sum(s.get("extra", {}).get("invalid_tool_calls", 0) for s in scores),
        "model_plan_correct": rate([e["model_plan_correct"] for e in plan_cases]),
        "recoveries": {
            "nudges": recov.count("nudge"),
            "system_plan_schedule": recov.count("system_plan_schedule"),
            "not_run": recov.count("not_run"),
            "cases_with_recovery": [s["id"] for s in scores if s.get("extra", {}).get("recoveries")],
        },
        "system_tool_calls": sum(e.get("system_tool_calls", 0) for e in ex),
        "unsupported_claims": {
            "runtime_flagged_in_final_answers": sum(e.get("runtime_unsupported_claims", 0) for e in ex),
            "audit_in_final_answers": sum(len(e.get("audit_unsupported_claims", [])) for e in ex),
            "audit_cases": [s["id"] for s in scores if s.get("extra", {}).get("audit_unsupported_claims")],
        },
        "rejected_section_mentions": {s["id"]: s["extra"]["rejected_section_mentions"] for s in scores
                                      if s.get("extra", {}).get("rejected_section_mentions")},
        "hard_constraint_violations": {"checked": ds is not None, "count": sum(map(len, violations.values())),
                                       "cases": violations},
        "latency_per_case_s": per_case_latency,
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


# ---------------------------------------------------------------- scoring v2

SCORING_V2_NOTE = (
    "v2 = all v1 criteria + structured answer assertions (evaluation/assertions.py): "
    "conflict, availability, ineligible, clarification, sections_ok, recommends_option, "
    "must_attempt, and academic_claims (no statement contradicting the dataset and no "
    "positive availability/eligibility statement without plan_schedule support)."
)


def score_case_v2(case: dict, record: dict, ds) -> dict:
    """v1 criteria plus stricter, sentence-level assertions. ds = the dataset the run used."""
    from evaluation import assertions as A

    score = score_case(case, record)
    if "error" in record:
        return {**score, "scoring_version": 2}
    expect = case.get("expect", {})
    result = record.get("result") or {}
    answer = result.get("answer") or ""
    trace = result.get("trace", [])
    titles = A.titles_of(ds)
    checks = score["checks"]

    def check(name, passed, detail=""):
        checks[name] = {"pass": bool(passed), "detail": detail}

    if "must_attempt" in expect:
        called = {t["tool"] for t in trace}
        missing = [t for t in expect["must_attempt"] if t not in called]
        check("must_attempt", not missing, f"missing={missing}")
    for a, b in expect.get("conflict", []):
        check(f"conflict:{a}/{b}", A.conflict(answer, a, b), "answer must say these two sections conflict")
    for course, state in expect.get("availability", {}).items():
        check(f"availability:{course}", A.availability(answer, course, state, titles), f"expected {state}")
    for course, missing in expect.get("ineligible", {}).items():
        check(f"ineligible:{course}", A.ineligible(answer, course, missing, titles),
              f"must say {course} needs {missing}")
    if "clarification" in expect:
        c = expect["clarification"]
        check("clarification", A.clarification(answer, c.get("candidates"), c.get("min", 0)),
              f"must ask a question naming >= {c.get('min', 0)} of {c.get('candidates')}")
    allowed = expect.get("allowed_sections")
    if allowed is None and "options" in expect:
        allowed = sorted({s for o in expect["options"] for s in o})
    if allowed is not None:
        ok, bad = A.sections_ok(answer, set(allowed), set(A.SECTION.findall(record.get("request", ""))))
        check("sections_ok", ok, f"sections outside the allowed set: {bad}")
    if expect.get("recommend") and expect.get("options"):
        check("recommends_option", A.recommends_option(answer, expect["options"]),
              "answer must name every section of at least one valid option")

    truth = A.truth_table(ds, record.get("student_id"), record.get("term_id"))
    false = A.false_claims(answer, truth, titles)
    unsupported = A.unsupported_claims(answer, trace, titles)
    check("academic_claims", not false and not unsupported, f"false={false} unsupported={unsupported}")
    score["extra"]["false_claims"] = false
    score["extra"]["unsupported_claims_v2"] = unsupported
    score["pass"] = all(c["pass"] for c in checks.values())
    score["scoring_version"] = 2
    return score


def summarize_v2(cases: list[dict], scores: list[dict], records: list[dict], ds) -> dict:
    s = summarize(cases, scores, records, ds)
    tokens_in = sum((c.get("prompt_tokens") or 0) for r in records for c in r.get("llm_calls", []))
    tokens_out = sum((c.get("output_tokens") or 0) for r in records for c in r.get("llm_calls", []))
    s["scoring_version"] = 2
    s["scoring_note"] = SCORING_V2_NOTE
    s["false_claims"] = {"count": sum(len(x.get("extra", {}).get("false_claims", [])) for x in scores),
                         "cases": [x["id"] for x in scores if x.get("extra", {}).get("false_claims")]}
    s["unsupported_claims_v2"] = {
        "count": sum(len(x.get("extra", {}).get("unsupported_claims_v2", [])) for x in scores),
        "cases": [x["id"] for x in scores if x.get("extra", {}).get("unsupported_claims_v2")]}
    s["tokens"] = {"prompt": tokens_in, "output": tokens_out}
    s["failed_cases"] = {x["id"]: [k for k, c in x["checks"].items() if not c["pass"]]
                         for x in scores if not x["pass"]}
    return s
