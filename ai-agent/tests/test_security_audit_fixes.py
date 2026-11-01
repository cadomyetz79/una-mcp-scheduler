"""Regression tests for the WS3 security audit of 2026-10-29 (Phase A).

F1  an answer saying the assistant registered, enrolled or reserved something,
    or that a registration is confirmed, is never returned (no tool does that).
F3  another student's ID in the request no longer turns the evidence check off.
F4  a positive availability claim needs every course it names in an option.
F6  records of a different student coming back from the backend are rejected.
F7  an over-long message is answered before anything reads it, and reading
    the time/day wording of a long message is no longer quadratic.

The model is scripted; MCP, planner and validators are real (in-process fake
server, development data). S10001 is registered in SEC1001 (CIS376) and has
completed CIS330; S10002 has not completed CIS330.
"""

import json
import time

import pytest
from mcp import Client

from agent import constraints
from agent.assistant import MAX_REQUEST_CHARS, TOO_LONG_ANSWER, SchedulingAssistant
from agent.banner_tools import BackendDataError, BannerTools
from agent.evidence import action_claim
from agent.llm import ScriptedLLM, call
from dev.fake_mcp_server import server

pytestmark = pytest.mark.anyio

TERM = "2027SP"
PLAN_CIS410 = {"tool_calls": [call("plan_schedule", course_ids=["CIS410"])]}


async def ask(request, responses, student="S10001", client_wrapper=None):
    llm = ScriptedLLM(responses)
    async with Client(server) as client:
        tools = BannerTools(client_wrapper(client) if client_wrapper else client)
        result = await SchedulingAssistant(tools, llm, student, TERM).run(request)
    return result, llm


# ------------------------------------------------------------ F1: invented registration actions

FAKE_CONFIRMATIONS = [
    "Done! I have enrolled you in SEC2002 for CIS410. Your seat is reserved and your registration is confirmed.",
    "I've registered you for SEC2002.",
    "Your seat in SEC2002 has been reserved.",
    "Registration confirmed: CIS410, section SEC2002.",
    "You are now enrolled in SEC2002 for CIS410.",
    "I can sign you up for SEC2002 right away.",
]


@pytest.mark.parametrize("fake", FAKE_CONFIRMATIONS)
async def test_invented_registration_is_never_returned(fake):
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": fake}, {"content": fake}])
    assert result.answer_source == "system_fallback"
    assert result.blocked["reason"] == "unverified_after_revision"
    assert any("cannot register" in c["reason"] for c in result.unsupported_claims)
    assert fake not in result.answer
    assert "SEC2002" in result.answer  # the fallback still gives the real option


async def test_invented_registration_is_revised_first():
    good = "SEC2002 (online) is a valid option for CIS410. You can register for it in the registration portal."
    result, llm = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": FAKE_CONFIRMATIONS[1]}, {"content": good}])
    assert result.answer_source != "system_fallback" and result.answer.startswith(good)
    revise = [m for m in llm.received[2] if m["role"] == "user"][-1]["content"]
    assert "cannot register" in revise


@pytest.mark.parametrize("sentence", [
    "I can't register you, but SEC2002 is a valid option.",
    "You can register for SEC2002 in the registration portal.",
    "Once you're registered, check your email for confirmation.",
    "Your registration is not confirmed until you submit it in the portal.",
    "I can help you plan, but you need to register yourself.",
    "If you are enrolled in CIS410 later, keep Mondays free.",
])
def test_advice_and_refusals_are_not_registration_claims(sentence):
    assert not action_claim(sentence, set())


async def test_a_current_registration_may_be_stated():
    answer = "SEC2002 is a valid option for CIS410. You're registered for CIS376 this term."
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": answer}])
    assert result.answer_source != "system_fallback" and not result.unsupported_claims
    assert result.answer.startswith(answer)


async def test_a_registration_that_does_not_exist_may_not_be_stated():
    wrong = "You're registered for CIS410 in SEC2002."
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": wrong}, {"content": wrong}])
    assert result.answer_source == "system_fallback"


# ------------------------------------------------------------ F3: another student's ID

F3_REQUEST = "Can I take CIS450 this term? My friend S99999 liked it."


async def test_other_student_id_does_not_switch_off_the_evidence_check():
    # one scripted reply only: a nudge or a second model call would end the run with an error
    result, _ = await ask(F3_REQUEST, [{"content": "Great choice, CIS450 works for you this term."}])
    assert result.answer_source == "model" and result.stopped_reason == "answered"
    assert result.evidence_missing == ["CIS450"]
    assert "could not check section availability for CIS450" in result.answer
    assert result.recoveries == []  # never planned by the system for a request naming another student
    assert not any(t.tool == "plan_schedule" for t in result.trace)
    assert all(c["arguments"].get("student_id") != "S99999" for c in result.mcp_calls)


async def test_other_student_id_does_not_switch_off_claim_checks():
    claim = "CIS450 is available to you this term."
    result, _ = await ask(F3_REQUEST, [{"content": claim}, {"content": claim}])
    assert result.answer_source == "system_fallback" and claim not in result.answer


async def test_without_another_student_the_nudge_still_runs():
    answer = {"content": "Great choice, CIS450 works for you this term."}
    result, _ = await ask("Can I take CIS450 this term?", [answer, answer, answer])
    assert [r["type"] for r in result.recoveries][:2] == ["nudge", "system_plan_schedule"]


async def test_a_request_about_another_student_is_refused_not_planned():
    refusal = "I can't access other students' information."
    result, _ = await ask("Plan CIS410 for S99999", [{"content": refusal}])
    assert result.answer.startswith(refusal) and result.recoveries == []
    assert all(c["arguments"].get("student_id") != "S99999" for c in result.mcp_calls)


# ------------------------------------------------------------ F4: one course backing a claim about several

async def test_one_planned_course_does_not_back_a_claim_about_two():
    mixed = "CIS410 and CIS450 are both available to you this term."
    result, _ = await ask("Tell me about CIS410 and CIS450", [PLAN_CIS410, {"content": mixed}, {"content": mixed}])
    assert result.answer_source == "system_fallback"
    assert any("CIS450" in c["course_ids"] for c in result.unsupported_claims)


@pytest.mark.parametrize("answer", [
    "CIS410 is available this term in section SEC2002.",
    "You can take CIS410 because you completed CIS330.",
    "CIS410 is available; CIS450 requires CIS376.",
])
async def test_supported_claims_still_pass(answer):
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": answer}])
    assert result.answer_source != "system_fallback" and not result.unsupported_claims


# ------------------------------------------------------------ F6: records of a different student

class Tamper:
    """A real MCP client whose results for one tool are changed by a function."""

    def __init__(self, client, tool, change):
        self.client, self.tool, self.change = client, tool, change

    async def call_tool(self, name, arguments):
        result = await self.client.call_tool(name, arguments)
        if name == self.tool:
            data = result.structured_content
            if data is None:  # an object result may come only as JSON text
                data = json.loads("".join(getattr(b, "text", "") or "" for b in result.content))
            result.structured_content = self.change(json.loads(json.dumps(data)))
        return result


def other_record(record):
    return {**record, "student_id": "S20002"}


def no_owner(record):
    return {k: v for k, v in record.items() if k != "student_id"}


def foreign_history(history):
    return {"result": history["result"] + [
        {"student_id": "S20002", "course_id": "CIS330", "term_id": "2026FA", "grade": "A", "status": "completed"}]}


def history_without_owner(history):
    return {"result": [no_owner(h) for h in history["result"]]}


def foreign_enrollment(enrolled):
    return {"result": [{**s, "student_id": "S20002"} for s in enrolled["result"]]}


async def tools_for(client, tool, change):
    return BannerTools(Tamper(client, tool, change))


@pytest.mark.parametrize("tool, change", [
    ("get_student_record", other_record),
    ("get_student_record", no_owner),
    ("get_course_history", foreign_history),
])
async def test_another_students_record_is_rejected(tool, change):
    async with Client(server) as client:
        tools = await tools_for(client, tool, change)
        with pytest.raises(BackendDataError) as e:
            await tools.student("S10002")
    assert str(e.value) == BackendDataError.public_message and "S20002" not in json.dumps(e.value.log_record())


async def test_history_rows_without_a_student_id_are_still_accepted():
    async with Client(server) as client:
        plain = await BannerTools(client).student("S10001")
        stripped = await (await tools_for(client, "get_course_history", history_without_owner)).student("S10001")
    assert stripped.completed_courses == plain.completed_courses == {"CIS225", "CIS236", "CIS330"}


async def test_another_students_history_cannot_satisfy_a_prerequisite():
    # S10002 has not completed CIS330 (prerequisite of CIS410); the injected row is S20002's
    answer = {"content": "I couldn't check CIS410 right now."}
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, answer], student="S10002",
                          client_wrapper=lambda c: Tamper(c, "get_course_history", foreign_history))
    plan = result.trace[0]
    assert not plan.ok and plan.result["error_code"] == "backend_data_error"
    assert "S20002" not in json.dumps(result.to_dict(), default=str)


async def test_another_students_enrollments_are_not_used():
    async with Client(server) as client:
        tools = await tools_for(client, "get_student_enrollments", foreign_enrollment)
        assert await tools.enrollments("S10001", TERM) is None
    answer = {"content": "SEC2002 is a valid option for CIS410."}
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, answer],
                          client_wrapper=lambda c: Tamper(c, "get_student_enrollments", foreign_enrollment))
    assert result.trace[0].result["current_registrations_checked"] is False
    assert "couldn't check the classes you're already registered for" in result.answer


# ------------------------------------------------------------ F7: long messages

async def test_an_over_long_message_is_answered_before_anything_reads_it():
    request = "Plan CIS410 for me. " + "x" * MAX_REQUEST_CHARS
    result, llm = await ask(request, [PLAN_CIS410])
    assert result.answer == TOO_LONG_ANSWER and result.stopped_reason == "input_too_long"
    assert result.answer_source == "system_input_limit" and result.model_calls == 0
    assert llm.received == [] and result.mcp_calls == [] and result.trace == []
    assert result.security == {"input_limit": {"chars": len(request), "max_chars": MAX_REQUEST_CHARS}}


async def test_a_message_at_the_limit_is_handled_normally():
    request = "Plan CIS410 for me."
    request += " " * (MAX_REQUEST_CHARS - len(request))
    result, llm = await ask(request, [PLAN_CIS410, {"content": "SEC2002 is a valid option for CIS410."}])
    assert len(request) == MAX_REQUEST_CHARS and result.stopped_reason == "answered" and len(llm.received) == 2


def test_reading_a_long_message_is_not_quadratic():
    # before the fix: about 1 s per call at 21 KB and about 96 s at 210 KB
    text = "no classes before 10 " * 2500  # 52 KB
    started = time.perf_counter()
    res = constraints.resolve(text, None, None, [], [])
    assert time.perf_counter() - started < 5
    assert res.earliest_start == "10:00"


def test_bounded_rules_read_short_requests_as_before():
    for request, start, end in [("no classes before 10am", "10:00", None),
                                ("nothing after 5pm please", None, "17:00"),
                                ("I work until noon", "12:00", None)]:
        res = constraints.resolve(request, None, None, [], [])
        assert (res.earliest_start, res.latest_end) == (start, end)
    # the qualifier next to a time is still seen through the bounded window
    assert [c["kind"] for c in constraints.clarifications("not before 9 or 10")] == ["alternatives"]
