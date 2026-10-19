"""Evaluation dataset and scorer (no model needed).

The oracle test is the important one: every case's ideal tool calls are run
through the REAL assistant, planner and MCP server, and must score 100%.
If the data or the planner changes, this fails and the dataset's
expectations have to be reviewed.
"""

import copy

import pytest

from agent.llm import OllamaLLM, ScriptedLLM
from dev.fake_mcp_server import server
from evaluation.run_eval import load_cases, run_case
from evaluation.scoring import score_case, summarize

pytestmark = pytest.mark.anyio

DATA = load_cases()
CASES = DATA["cases"]
BY_ID = {c["id"]: c for c in CASES}


def test_dataset_shape():
    assert 15 <= len(CASES) <= 20
    assert len({c["id"] for c in CASES}) == len(CASES)
    for c in CASES:
        assert {"id", "category", "student_id", "request", "expect", "oracle"} <= set(c)
        assert c["oracle"][-1].get("content"), f"{c['id']} oracle must end with an answer"
    categories = {c["category"] for c in CASES}
    assert {"soft_preference", "mandatory_preference", "privacy", "prompt_injection"} <= categories


@pytest.mark.parametrize("case_id", sorted(BY_ID))
async def test_oracle_scores_full_marks(case_id):
    case = BY_ID[case_id]
    record = await run_case(case, DATA["term_id"], ScriptedLLM(case["oracle"]), server)
    score = score_case(case, record)
    assert score["pass"], score["checks"]


async def oracle_record(case_id):
    case = BY_ID[case_id]
    return await run_case(case, DATA["term_id"], ScriptedLLM(case["oracle"]), server)


def wrong_e02():
    # What qwen3:8b actually did on 2026-10-19: a wish marked as mandatory.
    case = copy.deepcopy(BY_ID["E02"])
    case["oracle"][0]["tool_calls"][0]["arguments"]["required_preferences"] = ["earliest_start"]
    case["oracle"][-1]["content"] = "CIS376 has no section after 10am. SEC2002 is online, 9:30 is too early."
    return case


async def test_scorer_flags_wrong_mandatory_classification_without_check():
    case = wrong_e02()
    record = await run_case(case, DATA["term_id"], ScriptedLLM(case["oracle"]), server,
                            check_preference_language=False)
    score = score_case(BY_ID["E02"], record)
    assert not score["checks"]["required"]["pass"]
    assert not score["checks"]["outcome"]["pass"]  # CIS376 wrongly excluded
    assert not score["extra"]["model_required_correct"]
    assert score["checks"]["grounded"]["pass"]


async def test_preference_check_corrects_the_same_mistake():
    case = wrong_e02()
    record = await run_case(case, DATA["term_id"], ScriptedLLM(case["oracle"]), server)
    score = score_case(BY_ID["E02"], record)
    assert score["checks"]["required"]["pass"] and score["checks"]["outcome"]["pass"]
    assert not score["extra"]["model_required_correct"]  # the model's raw choice is still reported
    fix = score["extra"]["corrections"][0]
    assert fix["preference"] == "earliest_start" and fix["applied"] == "soft"
    assert "if possible" in fix["evidence"]


async def test_hard_constraint_check_finds_nothing_in_oracle_runs(ds):
    from evaluation.scoring import hard_constraint_violations

    for case_id in ("E01", "E03", "E05", "E07", "E14"):
        record = await oracle_record(case_id)
        assert hard_constraint_violations(record, ds) == []


def test_hard_constraint_check_catches_an_invalid_option(ds):
    from evaluation.scoring import hard_constraint_violations

    bad = {"student_id": "S10001", "term_id": "2027SP", "result": {"trace": [{
        "tool": "plan_schedule", "ok": True,
        "arguments": {"course_ids": ["CIS376", "CIS410"], "earliest_start": "10:00",
                      "required_preferences": ["earliest_start"]},
        "result": {"options": [{"section_ids": ["SEC1001", "SEC2001"]}, {"section_ids": ["SEC1002"]}]}}]}}
    found = hard_constraint_violations(bad, ds)
    assert "TIME_CONFLICT" in found[0]["issues"] and found[0]["required_preference_broken_by"] == ["SEC1001"]
    assert "SECTION_FULL" in found[1]["issues"]


async def test_scorer_flags_ungrounded_answer_and_missing_tool():
    case = copy.deepcopy(BY_ID["E01"])
    case["oracle"] = [{"content": "Take SEC1001 and SEC2001."}, {"content": "Take SEC2001."}]
    record = await run_case(case, DATA["term_id"], ScriptedLLM(case["oracle"]), server, check_evidence=False,
                            check_security=False)  # the output guard would replace the answer
    checks = score_case(BY_ID["E01"], record)["checks"]
    assert not checks["grounded"]["pass"]
    assert not checks["tool_use"]["pass"]
    assert not checks["course_ids"]["pass"]


def test_scorer_flags_foreign_student_and_run_errors():
    case = BY_ID["E15"]
    record = {"student_id": "S10001", "result": {
        "answer": "I can only see your record.", "grounded": True, "stopped_reason": "answered",
        "trace": [], "mcp_calls": [{"tool": "get_student_record", "arguments": {"student_id": "S10002"}}]}}
    assert not score_case(case, record)["checks"]["privacy"]["pass"]
    errored = score_case(case, {"student_id": "S10001", "error": "LLMError: killed"})
    assert not errored["pass"] and not errored["checks"]["completed"]["pass"]


async def test_summary_counts(ds):
    records = [await oracle_record("E01"), await oracle_record("E17")]
    records[0]["case_id"], records[1]["case_id"] = "E01", "E17"
    scores = [score_case(BY_ID["E01"], records[0]), score_case(BY_ID["E17"], records[1])]
    s = summarize(CASES, scores, records, ds)
    assert s["cases"] == {"passed": 2, "total": 2, "rate": 1.0}
    assert s["hard_constraint_violations"]["count"] == 0 and s["tool_call_correctness"]["total"] == 2
    assert s["criteria"]["grounded"]["total"] == 2 and s["latency_s"]["n"] == 2


async def test_ollama_think_and_num_ctx_are_sent_and_stats_recorded(monkeypatch):
    llm = OllamaLLM(model="m", host="localhost:11434", think=False, num_ctx=4096)
    sent = {}

    def fake_post(payload):
        sent.update(payload)
        return {"message": {"role": "assistant", "content": "hi", "thinking": ""},
                "prompt_eval_count": 900, "eval_count": 50, "prompt_eval_duration": 2e9,
                "eval_duration": 1e9, "load_duration": 0}

    monkeypatch.setattr(llm, "_post", fake_post)
    await llm.chat([{"role": "user", "content": "x"}], [])
    assert sent["think"] is False and sent["options"]["num_ctx"] == 4096
    assert llm.stats[0]["prompt_tokens"] == 900 and llm.stats[0]["prompt_s"] == 2.0


async def test_ollama_default_payload_unchanged(monkeypatch):
    llm = OllamaLLM(model="m", host="localhost:11434")
    sent = {}
    monkeypatch.setattr(llm, "_post", lambda p: sent.update(p) or {"message": {}})
    await llm.chat([], [])
    assert "think" not in sent and sent["options"] == {"temperature": 0.0}


async def test_compare_separates_system_effect_from_model_variance(tmp_path):
    import json as _json

    from evaluation.compare import compare, load_run

    wrong = wrong_e02()
    runs = {}
    for name, check in (("base", False), ("check", True)):
        d = tmp_path / name
        d.mkdir()
        for case in (wrong, BY_ID["E01"]):
            record = await run_case(case, DATA["term_id"], ScriptedLLM(case["oracle"]), server,
                                    check_preference_language=check)
            record["case_id"] = case["id"]
            (d / f"{case['id']}.json").write_text(_json.dumps({"record": record}))
        runs[name] = load_run(d, [BY_ID["E02"], BY_ID["E01"]])
    rows = {r["id"]: r for r in compare([BY_ID["E01"], BY_ID["E02"]], runs["base"], runs["check"])}
    assert rows["E02"]["change"] == "fixed" and rows["E02"]["cause"] == "system"
    assert rows["E02"]["model_required_correct"] == [False, False]
    assert rows["E01"]["change"] == "same"


def test_compare_labels_calls_added_after_a_recovery_as_intervention():
    from evaluation.compare import compare

    def rec(trace, recoveries=()):
        return {"record": {"result": {"trace": trace, "recoveries": list(recoveries)}, "wall_s": 1},
                "score": {"pass": False, "checks": {}, "extra": {}}}

    search = {"tool": "search_courses", "arguments": {"query": "CIS330"}, "ok": True, "result": []}
    plan = {"tool": "plan_schedule", "arguments": {"course_ids": ["CIS330"]}, "ok": True, "result": {}}
    a = {"E09": rec([search])}
    b = {"E09": rec([search, plan], [{"type": "nudge"}])}
    b["E09"]["score"]["pass"] = True
    c = {"E09": rec([plan])}
    assert compare([BY_ID["E09"]], a, b)[0]["cause"] == "intervention"
    assert compare([BY_ID["E09"]], a, c)[0]["cause"] == "model_variance"
