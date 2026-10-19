"""The system-run plan_schedule fallback (agent/assistant.py + agent/evidence.py).

In the live runs the model always followed the nudge, so the fallback never
ran. These tests make the scripted model IGNORE the nudge and check that the
fallback:
- only ever passes course IDs the student wrote (or the single search hit),
  never preferences, mandatory flags or other invented arguments;
- runs at most once and never for another student;
- does not run when it would leave out the student's own time/day wishes;
- reports failure (missing data, MCP errors) instead of an answer, and
  cannot turn an ineligible or invalid schedule into a valid one.
"""

import pytest
from mcp import Client

from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.llm import ScriptedLLM, call
from dev.fake_mcp_server import server
from evaluation.scoring import hard_constraint_violations

pytestmark = pytest.mark.anyio

TERM = "2027SP"
IGNORE = {"content": "Sure, that works."}


async def ask(request, responses, student="S10001", security=True):
    llm = ScriptedLLM(responses)
    async with Client(server) as client:
        assistant = SchedulingAssistant(BannerTools(client), llm, student, TERM, check_security=security)
        result = await assistant.run(request)
    return result, llm


def system_calls(result):
    return [t for t in result.trace if t.by == "system"]


def record(result, student="S10001"):
    return {"student_id": student, "term_id": TERM, "result": result.to_dict()}


async def test_fallback_passes_only_the_course_ids_from_the_request(ds):
    result, llm = await ask("Plan CIS376 and CIS410 for me.",
                            [IGNORE, IGNORE, {"content": "SEC1001 with SEC2002 is the valid option."}])
    (sys_call,) = system_calls(result)
    assert sys_call.arguments == {"course_ids": ["CIS376", "CIS410"]}  # nothing else invented
    applied = sys_call.result["preferences_applied"]
    assert applied == {"earliest_start": None, "latest_end": None, "avoid_days": [], "required": []}
    assert hard_constraint_violations(record(result), ds) == []
    assert result.grounded and result.model_calls == 3


async def test_fallback_after_partial_plan_uses_the_full_request():
    # The model planned only one of the two requested courses, then ignored the nudge.
    result, _ = await ask("Plan CIS376 and CIS410.", [
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376"])]},
        {"content": "CIS376 is open in SEC1001."},
        {"content": "CIS376 is open in SEC1001."},
        {"content": "SEC1001 with SEC2002 is valid."},
    ])
    assert [t.arguments for t in system_calls(result)] == [{"course_ids": ["CIS376", "CIS410"]}]


async def test_fallback_cannot_make_an_ineligible_course_valid(ds):
    # S10002 lacks CIS330. The model ignores the nudge and keeps claiming eligibility.
    claim = {"content": "You can take CIS376 next spring."}
    result, llm = await ask("Plan CIS376 for me.", [IGNORE, IGNORE, claim, claim], student="S10002")
    (sys_call,) = system_calls(result)
    assert sys_call.result["options"] == []
    assert sys_call.result["excluded"][0]["code"] == "MISSING_PREREQUISITE"
    assert result.unsupported_claims[0]["course_ids"] == ["CIS376"]  # the model's claim, recorded
    # The claim never reaches the student: the answer is built from the planner result.
    assert result.answer_source == "system_fallback" and "You can take" not in result.answer
    assert "CIS376: CIS376 requires CIS330." in result.answer
    assert hard_constraint_violations(record(result, "S10002"), ds) == []
    flagged, _ = await ask("Plan CIS376 for me.", [IGNORE, IGNORE, claim, claim], student="S10002",
                           security=False)
    assert not flagged.grounded and flagged.answer == claim["content"]


async def test_fallback_with_unknown_course_invents_nothing():
    result, _ = await ask("Add CIS999 to my spring schedule.",
                          [IGNORE, IGNORE, {"content": "CIS999 does not exist in the catalog."}])
    (sys_call,) = system_calls(result)
    assert sys_call.result["options"] == [] and sys_call.result["excluded"][0]["code"] == "UNKNOWN_COURSE"
    assert result.grounded


async def test_fallback_reports_missing_mcp_data_instead_of_answering():
    # Bound student does not exist in the backend: every plan_schedule fails.
    claim = {"content": "You can take CIS410 next spring."}
    result, _ = await ask("Plan CIS410 for me.", [IGNORE, IGNORE, claim, claim], student="S29999")
    (sys_call,) = system_calls(result)
    assert not sys_call.ok and "not found" in sys_call.result["error"]
    assert result.evidence_missing == ["CIS410"]
    # the unsupported claim is replaced by what is known: the record is missing
    assert result.answer_source == "system_fallback" and "You can take" not in result.answer
    assert "couldn't find your student record" in result.answer
    flagged, _ = await ask("Plan CIS410 for me.", [IGNORE, IGNORE, claim, claim], student="S29999",
                           security=False)
    assert "could not check section availability" in flagged.answer and not flagged.grounded


async def test_no_fallback_when_it_would_drop_the_students_time_wish():
    # (third response: "Sure, that works." confirms an unplanned request, so it gets one revision)
    result, _ = await ask("Plan CIS376 and CIS410, but I can't do anything before 10am.", [IGNORE] * 3)
    assert system_calls(result) == []
    assert [r["type"] for r in result.recoveries] == ["nudge", "not_run"]
    assert result.evidence_missing == ["CIS376", "CIS410"]


async def test_no_fallback_for_another_students_request():
    result, _ = await ask("Plan CIS376 for student S10002.", [IGNORE, IGNORE])
    assert system_calls(result) == [] and result.recoveries == []
    assert result.answer_source == "system_fallback"  # "Sure, that works." confirmed nothing verified
    assert all(c["arguments"].get("student_id") != "S10002" for c in result.mcp_calls)


async def test_no_fallback_without_known_course_ids():
    # No IDs in the request and no search: the inputs are missing, so nothing runs.
    result, _ = await ask("Put me in the security class next spring.", [IGNORE])
    assert system_calls(result) == [] and result.recoveries == []


async def test_fallback_after_invalid_arguments():
    result, llm = await ask("Plan CIS376 and CIS410 in sections SEC1001 and SEC2001.", [
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"], section_ids=["SEC1001"])]},
        {"content": "Would you like me to continue?"},
        {"content": "Would you like me to continue?"},
        {"content": "SEC1001 and SEC2001 conflict. SEC1001 with SEC2002 works."},
    ])
    assert not result.trace[0].ok
    assert [t.arguments for t in system_calls(result)] == [{"course_ids": ["CIS376", "CIS410"]}]
    assert result.grounded and result.rejected_section_mentions == ["SEC2001"]


async def test_fallback_runs_at_most_once():
    result, llm = await ask("Plan CIS376.", [IGNORE] * 6)
    assert len(system_calls(result)) == 1
    assert [r["type"] for r in result.recoveries] == ["nudge", "system_plan_schedule"]
    assert result.model_calls == 3


def test_claim_by_course_title_is_checked_when_the_title_came_from_search():
    from agent.evidence import unsupported_claims

    search = [{"tool": "search_courses", "ok": True, "arguments": {"query": "secure"},
               "result": [{"course_id": "CIS410", "title": "Secure Systems"}]}]
    assert unsupported_claims("Secure Systems is offered next spring.", search)[0]["course_ids"] == ["CIS410"]
    assert unsupported_claims("Data Mining is offered next spring.", search) == []  # unknown title: not recognised
