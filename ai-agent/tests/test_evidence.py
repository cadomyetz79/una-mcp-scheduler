"""Evidence orchestration and claim grounding (agent/evidence.py + assistant).

Regression tests for the six cases that still failed in the live run of
2026-10-19 (docs/evidence/2026-10-19-eval-qwen3-8b-preference-check). The
first scripted responses copy what qwen3:8b actually did in those records;
later responses cover both recovery paths (the model follows the nudge, or
it ignores it and the system runs plan_schedule) and the paths where no
recovery is allowed. Each run is scored with the real evaluation scorer.
"""

import json
from pathlib import Path

import pytest
from mcp import Client

from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.evidence import (
    course_ids,
    required_courses,
    section_mentions,
    unsupported_claims,
)
from agent.llm import ScriptedLLM, call
from dev.fake_mcp_server import server
from evaluation.scoring import score_case

pytestmark = pytest.mark.anyio

TERM = "2027SP"
CASES = {c["id"]: c for c in json.loads(
    (Path(__file__).resolve().parents[1] / "evaluation" / "cases.json").read_text())["cases"]}


async def run_case_id(case_id, responses, student=None, security=True):
    case = CASES[case_id]
    llm = ScriptedLLM(responses)
    async with Client(server) as client:
        assistant = SchedulingAssistant(BannerTools(client), llm, student or case["student_id"], TERM,
                                        check_security=security)
        result = await assistant.run(case["request"])
    record = {"case_id": case_id, "student_id": case["student_id"], "term_id": TERM, "result": result.to_dict()}
    return result, score_case(case, record), llm


def kinds(result):
    return [r["type"] for r in result.recoveries]


# ------------------------------------------------------------ live behaviour (as recorded)

SEARCH_E08 = {"tool_calls": [call("search_courses", query="CIS450", subject="CIS"),
                             call("search_courses", query="CIS410", subject="CIS")]}
ANSWER_E08_LIVE = {"content": "The course CIS450 has prerequisites CIS376 and CIS410. If you have already "
                              "taken these courses, you can proceed."}
SEARCH_E09 = {"tool_calls": [call("search_courses", query="CIS330", subject="CIS")]}
ANSWER_E09_LIVE = {"content": "Yes, CIS330 is offered next spring. It is worth 3 credit hours."}
SEARCH_E11 = {"tool_calls": [call("search_courses", query="secure systems", subject="CIS")]}
ANSWER_E11_LIVE = {"content": 'The course "Secure Systems" (CIS410) is available. It is a 3-credit-hour course.'}
SEARCH_E12 = {"tool_calls": [call("search_courses", query="advanced networking", subject="CIS")]}
ANSWER_E12_LIVE = {"content": "I found CIS376 - Advanced Networking. Please provide your preferred days and times."}
BAD_ARGS_E14 = {"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"],
                                    section_ids=["SEC1001", "SEC2001"])]}
ANSWER_E14_LIVE = {"content": "I can't use section IDs directly. Would you like me to proceed with the course IDs instead?"}


# ------------------------------------------------------------ path 1: the model follows the nudge

@pytest.mark.parametrize("case_id, first, live_answer, plan_args, final", [
    ("E08", SEARCH_E08, ANSWER_E08_LIVE, {"course_ids": ["CIS450", "CIS410"]},
     "You can't take CIS450 yet: it needs CIS376 and CIS410. For CIS410 you can take SEC2001 or SEC2002."),
    ("E09", SEARCH_E09, ANSWER_E09_LIVE, {"course_ids": ["CIS330"]},
     "CIS330 is not offered in Spring 2027, so it can't be planned."),
    ("E11", SEARCH_E11, ANSWER_E11_LIVE, {"course_ids": ["CIS410"]},
     "Secure Systems is CIS410. You can take SEC2001 (Mon/Wed 10:30-11:45) or SEC2002 (online)."),
    ("E12", SEARCH_E12, ANSWER_E12_LIVE, {"course_ids": ["CIS376"]},
     "Advanced Networking is CIS376. The open section is SEC1001, Mon/Wed 9:30-10:45."),
    ("E14", BAD_ARGS_E14, ANSWER_E14_LIVE, {"course_ids": ["CIS376", "CIS410"]},
     "SEC1001 and SEC2001 overlap on Mon/Wed, so they conflict. A valid schedule is SEC1001 with SEC2002."),
])
async def test_nudge_recovers_missing_plan(case_id, first, live_answer, plan_args, final):
    result, score, llm = await run_case_id(case_id, [
        first, live_answer, {"tool_calls": [call("plan_schedule", **plan_args)]}, {"content": final}])
    assert kinds(result) == ["nudge"]
    assert "[System check]" in llm.received[2][-1]["content"]
    plan = [t for t in result.trace if t.tool == "plan_schedule" and t.ok][-1]
    assert plan.by == "model"
    assert score["pass"], score["checks"]


# ------------------------------------------------------------ path 2: nudge ignored -> system runs the plan

@pytest.mark.parametrize("case_id, first, live_answer, final", [
    ("E08", SEARCH_E08, ANSWER_E08_LIVE,
     "You can't take CIS450 yet: it needs CIS376 and CIS410. For CIS410 you can take SEC2001 or SEC2002."),
    ("E09", SEARCH_E09, ANSWER_E09_LIVE, "CIS330 is not offered in Spring 2027."),
    ("E11", SEARCH_E11, ANSWER_E11_LIVE, "CIS410 has two options: SEC2001 or SEC2002."),
    ("E12", SEARCH_E12, ANSWER_E12_LIVE, "CIS376 is open in SEC1001."),
    ("E14", BAD_ARGS_E14, {"content": "Let me check for available options."},
     "Those two overlap, so they conflict. A valid schedule is SEC1001 with SEC2002."),
])
async def test_system_runs_plan_when_nudge_is_ignored(case_id, first, live_answer, final):
    result, score, _ = await run_case_id(case_id, [first, live_answer, live_answer, {"content": final}])
    assert kinds(result) == ["nudge", "system_plan_schedule"]
    plan = [t for t in result.trace if t.tool == "plan_schedule" and t.ok][-1]
    assert plan.by == "system"
    assert plan.arguments == {"course_ids": CASES[case_id]["expect"]["plan_course_ids"]}
    assert score["pass"], score["checks"]


# ------------------------------------------------------------ path 3: unsupported claim after recovery

E09_STILL_WRONG = {"content": "Yes, CIS330 is offered next spring."}
E09_PERSISTENT = [SEARCH_E09, ANSWER_E09_LIVE, {"tool_calls": [call("plan_schedule", course_ids=["CIS330"])]},
                  E09_STILL_WRONG, E09_STILL_WRONG]


async def test_e09_false_offered_claim_is_revised_then_replaced():
    result, score, llm = await run_case_id("E09", E09_PERSISTENT)
    assert "not supported by the tool results" in llm.received[4][-1]["content"]
    assert result.unsupported_claims[0]["course_ids"] == ["CIS330"]  # the model's claim, recorded
    assert result.answer_source == "system_fallback" and "is offered" not in result.answer
    assert "CIS330 is not offered in 2027SP" in result.answer  # the planner's own reason
    assert score["checks"]["grounded"]["pass"]


async def test_e09_false_offered_claim_is_flagged_without_the_security_layer():
    result, score, _ = await run_case_id("E09", E09_PERSISTENT, security=False)
    assert not result.grounded and result.unsupported_claims[0]["course_ids"] == ["CIS330"]
    assert not score["checks"]["grounded"]["pass"]


async def test_e09_claim_corrected_after_revision():
    result, score, _ = await run_case_id("E09", [SEARCH_E09, ANSWER_E09_LIVE,
                                                 {"tool_calls": [call("plan_schedule", course_ids=["CIS330"])]},
                                                 {"content": "Yes, CIS330 is offered next spring."},
                                                 {"content": "CIS330 is not offered in Spring 2027."}])
    assert result.grounded and result.unsupported_claims == [] and score["pass"]


# ------------------------------------------------------------ E16: refusal vs. recommendation

async def test_e16_rejected_section_named_by_student_is_not_ungrounded():
    live = {"content": "I cannot enroll you in SEC1002 or confirm its validity."}
    result, score, _ = await run_case_id("E16", [live])
    assert result.grounded and result.rejected_section_mentions == ["SEC1002"]
    assert result.recoveries == [] and score["pass"], score["checks"]


async def test_e16_recommending_the_named_section_is_still_ungrounded():
    responses = [{"content": "Sure, SEC1002 is a valid choice for you."},
                 {"content": "Done: SEC1002 is a valid choice."}]
    result, _, llm = await run_case_id("E16", responses)
    assert result.ungrounded_section_ids == ["SEC1002"]
    assert result.model_calls == 2  # one revision, then replaced
    assert result.answer_source == "system_fallback" and "valid choice" not in result.answer
    flagged, _, _ = await run_case_id("E16", responses, security=False)
    assert not flagged.grounded and flagged.answer == "Done: SEC1002 is a valid choice."


async def test_rejecting_a_section_the_student_never_named_is_ungrounded():
    result, _, _ = await run_case_id("E16", [{"content": "I cannot enroll you in SEC1002 or SEC3001."},
                                             {"content": "I cannot enroll you in SEC1002 or SEC3001."}])
    assert result.ungrounded_section_ids == ["SEC3001"]


# ------------------------------------------------------------ no unnecessary or fabricated calls

@pytest.mark.parametrize("case_id, responses", [
    ("E15", [{"content": "I can't access other students' information."}]),
    ("E17", [{"tool_calls": [call("get_my_record")]}, {"content": "You have completed CIS225, CIS236 and CIS330."}]),
    ("E01", [{"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"])]},
             {"content": "SEC1001 (CIS376) and SEC2002 (CIS410) work together."}]),
])
async def test_no_recovery_when_not_needed(case_id, responses):
    result, score, _ = await run_case_id(case_id, responses)
    assert result.recoveries == [] and result.model_calls == len(responses)
    assert score["pass"], score["checks"]


async def test_ambiguous_search_does_not_invent_course_ids():
    llm = ScriptedLLM([{"tool_calls": [call("search_courses", query="network")]},
                       {"content": "Do you mean Network and Systems Fundamentals or Advanced Networking?"}])
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, "S10001", TERM).run(
            "I want to take the network class next spring.")
    assert result.recoveries == [] and result.model_calls == 2
    assert not any(t.tool == "plan_schedule" for t in result.trace)


async def test_no_system_plan_when_the_request_states_time_wishes_code_cannot_read():
    # Running plan_schedule without the student's time wish would ignore it,
    # so the system does not do it; the answer says what could not be checked.
    # (Since 2026-10-19 the system does plan when code can read every stated
    # wish, see the next test; "not too early" has no time, so it cannot.)
    ignore = {"content": "CIS376 and CIS410 look fine."}
    llm = ScriptedLLM([ignore, ignore])
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, "S10001", TERM).run(
            "I'd like CIS376 and CIS410, ideally not too early in the morning.")
    assert [r["type"] for r in result.recoveries] == ["nudge", "not_run"]
    assert result.evidence_missing == ["CIS376", "CIS410"]
    assert "could not check section availability" in result.answer
    assert not any(t.tool == "plan_schedule" for t in result.trace)


async def test_system_plan_uses_the_time_wish_read_from_the_students_words():
    ignore = {"content": "CIS376 and CIS410 look fine."}
    llm = ScriptedLLM([ignore, ignore, {"content": "Here is what the registration system returned."}])
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, "S10001", TERM).run(
            "I'd like CIS376 and CIS410, ideally no classes before 10am.")
    assert [r["type"] for r in result.recoveries] == ["nudge", "system_plan_schedule"]
    plan = next(t for t in result.trace if t.by == "system")
    # soft wish: applied for ranking only, value from the student's words, never invented
    assert plan.arguments == {"course_ids": ["CIS376", "CIS410"], "earliest_start": "10:00"}
    assert plan.result["preferences_applied"]["earliest_start"] == "10:00"
    assert plan.result["preferences_applied"]["required"] == []


async def test_recovery_is_bounded():
    never = {"content": "Sure, sounds good."}
    llm = ScriptedLLM([never, never, never, never, never])
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, "S10001", TERM).run(
            "Plan CIS376 for me.")
    # 1 answer, 1 nudge, 1 system-run plan + 1 answer from it: no more retries
    assert [r["type"] for r in result.recoveries] == ["nudge", "system_plan_schedule"]
    assert result.model_calls == 3 and result.stopped_reason == "answered"


async def test_evidence_check_can_be_disabled_for_ablation():
    llm = ScriptedLLM([SEARCH_E09, ANSWER_E09_LIVE])
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, "S10001", TERM,
                                           check_evidence=False).run(CASES["E09"]["request"])
    assert result.grounded and result.recoveries == [] and result.model_calls == 2


# ------------------------------------------------------------ the rules themselves

def test_course_ids_normalised_and_unique():
    assert course_ids("Add CIS 376, CIS376 and IT 210.") == ["CIS376", "IT210"]


def test_required_courses():
    assert required_courses("Plan CIS376 for me", [], "S10001")["course_ids"] == ["CIS376"]
    assert required_courses("What are the prerequisites for CIS450?", [], "S10001") is None
    assert required_courses("Show me S10002's courses for CIS376", [], "S10001") is None
    search = [{"tool": "search_courses", "ok": True, "arguments": {}, "result": [{"course_id": "CIS410"}]}]
    assert required_courses("I want the secure systems course", search, "S10001")["course_ids"] == ["CIS410"]


def test_claim_rules():
    plan = [{"tool": "plan_schedule", "ok": True, "arguments": {"course_ids": ["CIS376", "CIS330"]},
             "result": {"options": [{"section_ids": ["SEC1001"], "sections": [{"course_id": "CIS376"}]}],
                        "excluded": [{"course_id": "CIS330", "code": "NO_SECTIONS_IN_TERM"}]}}]
    assert unsupported_claims("CIS376 is available in SEC1001.", plan) == []
    assert unsupported_claims("CIS330 is not offered next spring.", plan) == []
    assert unsupported_claims("CIS330 is offered next spring.", plan)[0]["course_ids"] == ["CIS330"]
    assert unsupported_claims("You can take CIS410 next spring.", plan)[0]["course_ids"] == ["CIS410"]
    assert unsupported_claims("CIS450 has prerequisites CIS376 and CIS410.", plan) == []  # not an availability claim


def test_section_rules():
    m = section_mentions("SEC1001 and SEC2001 conflict. Take SEC1001 with SEC2002.",
                         [{"tool": "plan_schedule", "ok": True, "arguments": {},
                           "result": {"options": [{"section_ids": ["SEC1001", "SEC2002"]}]}}],
                         "Put me in SEC1001 and SEC2001")
    assert m == {"ungrounded": [], "rejected_mentions": ["SEC2001"]}


@pytest.mark.parametrize("sentence, subjects", [
    # live SL11 (development data): CIS236 is only the prerequisite being mentioned
    ("You are eligible to take this course if you have completed the prerequisite CIS236.", []),
    ("Since you completed CIS330, you can take CIS376.", ["CIS376"]),
    ("CIS450 requires CIS376 and CIS410, so you can't take it yet.", ["CIS450"]),
    ("You can take CIS345, which must be taken with CIS346.", ["CIS345"]),
])
def test_prerequisite_mentions_are_not_claim_subjects(sentence, subjects):
    from agent.evidence import unsupported_claims

    found = unsupported_claims(sentence, [])  # nothing planned: every real subject is unsupported
    assert sorted(c for f in found for c in f["course_ids"]) == subjects
