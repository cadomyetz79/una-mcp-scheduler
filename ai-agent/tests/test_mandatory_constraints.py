"""Regression tests for H1 (audit 2026-10-29): mandatory time/day limits.

Two distinct failure modes, both fixed on fix/ws3-h1-mandatory-constraints:

1. Named sections bypassed mandatory limits. check_requested_sections() ran
   only validate_schedule(), so "I can't do Mondays. Can I take SEC1001 with
   SEC2002?" reported valid_together=True although SEC1001 meets on Monday,
   and the answer "Yes, they work together" passed every guard.
2. Day codes were not read. "MWF", "M/W", "Tu/Th", "TR" named no day for
   preference_language/constraints, so unmentioned() DROPPED the model's
   correct avoid_days and options meeting on those days came back as valid.

Mock data (term 2027SP): SEC1001 = CIS376, MON/WED 09:30-10:45, open;
SEC2002 = CIS410, no scheduled meetings, open. Current registrations are
emptied (tmp copy of data/) so the result depends only on the limits.
"""

import json
import shutil

import pytest
from mcp import Client

import dev.fake_mcp_server as fake
from agent import constraints
from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.llm import ScriptedLLM, call
from agent.planner import Preferences, plan_schedules
from agent.preference_language import classify, expand_day_codes, unmentioned
from dev.stdio_server import DEFAULT_DATA_DIR

pytestmark = pytest.mark.anyio

TERM = "2027SP"
COURSES = ["CIS376", "CIS410"]
YES = "Yes, SEC1001 and SEC2002 work together for you."


@pytest.fixture
def no_registrations(tmp_path, monkeypatch):
    data = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, data)
    (data / "enrollments.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(fake, "DATA_DIR", data)
    return data


async def plan(prefs, sections=("SEC1001", "SEC2002")):
    async with Client(fake.server) as client:
        return await plan_schedules(BannerTools(client), "S10001", TERM, COURSES, prefs,
                                    requested_sections=list(sections))


async def ask(request, *replies):
    async with Client(fake.server) as client:
        assistant = SchedulingAssistant(BannerTools(client), ScriptedLLM(list(replies)), "S10001", TERM)
        return await assistant.run(request)


def plan_result(result):
    return next(t.result for t in result.trace if t.tool == "plan_schedule")


# ------------------------------------------------------------------ 1. named sections


@pytest.mark.parametrize("prefs, preference, message", [
    (Preferences(avoid_days=("MON",), required=("avoid_days",)), "avoid_days",
     "SEC1001 (CIS376) meets on MON, a day you said you need to keep free."),
    (Preferences(earliest_start="10:00", required=("earliest_start",)), "earliest_start",
     "SEC1001 (CIS376) starts before 10:00, the earliest time you said you can start."),
    (Preferences(latest_end="10:00", required=("latest_end",)), "latest_end",
     "SEC1001 (CIS376) ends after 10:00, the time you said you need to be done by."),
])
async def test_named_section_breaking_a_required_limit_is_not_valid(no_registrations, prefs, preference, message):
    result = await plan(prefs)
    rs = result.requested_sections
    assert rs["valid_together"] is False
    assert rs["issues"] == [{"code": "REQUIRED_PREFERENCE_VIOLATION", "preference": preference,
                             "message": message, "section_ids": ["SEC1001"]}]
    # the options were already filtered by the same limit
    assert result.options and all("SEC1001" not in o["section_ids"] for o in result.options)


async def test_soft_preference_does_not_block_named_sections(no_registrations):
    result = await plan(Preferences(avoid_days=("MON",), required=()))
    assert result.requested_sections["valid_together"] is True
    assert result.requested_sections["issues"] == []


async def test_one_issue_per_section_and_limit(no_registrations):
    # SEC1001 meets on MON and WED in one meeting: one avoid_days issue naming both days
    result = await plan(Preferences(avoid_days=("MON", "WED"), required=("avoid_days",)), sections=("SEC1001",))
    [issue] = result.requested_sections["issues"]
    assert issue["message"] == "SEC1001 (CIS376) meets on MON, WED, a day you said you need to keep free."


async def test_unrestricted_named_sections_are_unchanged(no_registrations):
    result = await plan(Preferences(required=()))
    assert result.requested_sections["valid_together"] is True
    assert result.requested_sections["in_returned_options"] is True


async def test_mandatory_limit_cannot_be_bypassed_by_naming_sections(no_registrations):
    # The model leaves the limit out and confirms the named sections twice. Code reads
    # "can't do Mondays", applies it, and the confirmation never reaches the student.
    result = await ask(
        "I want CIS376 and CIS410. I can't do Mondays. Can I take SEC1001 with SEC2002?",
        {"tool_calls": [call("plan_schedule", course_ids=COURSES)]},
        {"content": YES},
        {"content": YES},
    )
    res = plan_result(result)
    assert res["preferences_applied"]["avoid_days"] == ["MON"]
    assert res["preferences_applied"]["required"] == ["avoid_days"]
    assert res["requested_sections"]["valid_together"] is False
    assert result.answer_source == "system_fallback"
    assert YES not in result.answer
    assert "SEC1001 (CIS376) meets on MON" in result.answer


async def test_answer_that_omits_the_violation_gets_a_system_note(no_registrations):
    result = await ask(
        "I want CIS376 and CIS410. I can't do Mondays. Can I take SEC1001 with SEC2002?",
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, avoid_days=["MON"],
                             required_preferences=["avoid_days"])]},
        {"content": "SEC2002 is available for CIS410."},
    )
    assert result.answer_source == "model+system_note"
    assert result.answer.startswith("About the sections you named: SEC1001 (CIS376) meets on MON")


# ------------------------------------------------------------------ 2. day codes


@pytest.mark.parametrize("text, expected", [
    ("MWF", "Mon/Wed/Fri"), ("MW", "Mon/Wed"), ("TR", "Tue/Thu"), ("TTh", "Tue/Thu"), ("TuTh", "Tue/Thu"),
    ("TTH", "Tue/Thu"), ("MTWRF", "Mon/Tue/Wed/Thu/Fri"), ("M/W", "Mon/Wed"), ("M/W/F", "Mon/Wed/Fri"),
    ("Tu/Th", "Tue/Thu"), ("tu/th", "Tue/Thu"), ("T/R", "Tue/Thu"), ("T/Th", "Tue/Thu"), ("Mon/Wed", "Mon/Wed"),
    ("MW and TR", "Mon/Wed and Tue/Thu"),
])
def test_day_codes_are_expanded(text, expected):
    assert expand_day_codes(text) == expected


@pytest.mark.parametrize("text", [
    "WTF is this", "SAT prep", "Mr Smith", "w/o Fridays", "FT job", "I said TT", "M", "S", "mwf", "tr",
    "CIS376 SEC1001", "I want CIS376 and CIS410.",
])
def test_other_words_are_left_alone(text):
    assert expand_day_codes(text) == text


@pytest.mark.parametrize("request_text, days", [
    ("I can't do MWF.", ("MON", "WED", "FRI")),
    ("I can't do M/W.", ("MON", "WED")),
    ("I can't do Tu/Th.", ("TUE", "THU")),
    ("I can't take TR classes.", ("TUE", "THU")),
    ("I must keep MWF free.", ("MON", "WED", "FRI")),
])
def test_day_codes_are_read_as_mandatory_limits(request_text, days):
    reading = constraints.extract(request_text)["avoid_days"]
    assert (reading.mentioned, reading.reliable, reading.value, reading.verdict) == (True, True, days, "required")
    assert classify(request_text)["avoid_days"]["verdict"] == "required"
    assert unmentioned(request_text, ["avoid_days"]) == []


def test_soft_day_code_stays_soft():
    request_text = "If possible no MWF classes."
    assert constraints.extract(request_text)["avoid_days"].verdict == "soft"
    assert classify(request_text)["avoid_days"]["verdict"] == "soft"


@pytest.mark.parametrize("request_text, days", [
    ("I can't do MWF.", ["MON", "WED", "FRI"]),
    ("I can't do M/W.", ["MON", "WED"]),
])
async def test_model_value_for_day_code_is_kept(no_registrations, request_text, days):
    # before: unmentioned() dropped the model's correct avoid_days and SEC1001 (MON/WED) came back
    result = await ask(
        f"I want CIS376 and CIS410. {request_text}",
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, avoid_days=days,
                             required_preferences=["avoid_days"])]},
        {"content": "SEC2002 is the option."},
    )
    res = plan_result(result)
    assert "preferences_dropped" not in res
    assert res["preferences_applied"]["avoid_days"] == days
    assert res["preferences_applied"]["required"] == ["avoid_days"]
    assert [o["section_ids"] for o in res["options"]] == [["SEC2002"]]


async def test_day_code_left_out_by_the_model_is_applied(no_registrations):
    result = await ask(
        "I want CIS376 and CIS410. I can't do MWF.",
        {"tool_calls": [call("plan_schedule", course_ids=COURSES)]},
        {"content": "SEC2002 is the option."},
    )
    res = plan_result(result)
    assert res["preferences_applied"]["avoid_days"] == ["MON", "WED", "FRI"]
    assert res["preferences_applied"]["required"] == ["avoid_days"]
    assert all("SEC1001" not in o["section_ids"] for o in res["options"])
    assert json.dumps(res["constraint_changes"]).count("the model left out a constraint") == 1
