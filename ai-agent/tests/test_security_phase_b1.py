"""Security audit Phase B1 (2026-10-31): F12 and F8.

F12 plan_schedule checked earliest_start / latest_end with "^HH:MM$" and
    re.match, where "$" also matches before a final newline and "\\d" matches
    non-ASCII digits. "10:00\\n" or "1٩:00" passed the assistant's check, then
    the planner's parse_time (fullmatch, ASCII, data-validation F4) raised
    ValueError, which ended the whole request as a system error. The tool now
    validates with parse_time itself, so a bad value is an argument error the
    model can correct.
F8  constraints._Extractor.parse had @lru_cache(maxsize=None) on the method:
    one cache for the whole process whose keys kept every extractor, and so
    every student's request text, alive forever. The cache is now per
    extractor and goes away with it.
"""

import gc
import weakref

import pytest
from mcp import Client

from agent import constraints
from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.llm import ScriptedLLM, call
from dev.fake_mcp_server import server

pytestmark = pytest.mark.anyio

TERM = "2027SP"
COURSES = ["CIS376", "CIS410"]


async def run(responses, request):
    async with Client(server) as client:
        assistant = SchedulingAssistant(BannerTools(client), ScriptedLLM(responses), "S10001", TERM)
        return await assistant.run(request)


# ---------------------------------------------------------------- F12


@pytest.mark.parametrize("value", ["10:00\n", "1٩:00", " 10:00", "10:00 ", "10:00\r\n", "9:00", "24:00"])
async def test_f12_bad_time_is_an_argument_error_not_a_system_error(value):
    # vague wording: no time the code can read, so the model's value would reach the planner
    result = await run([
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, earliest_start=value)]},
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, earliest_start="10:00")]},
        {"content": "Option 1: SEC1001 + SEC2002."},
    ], "Plan CIS376 and CIS410, I'd like to start later in the day.")
    assert result.stopped_reason == "answered" and result.answer_source != "system_error"
    first = result.trace[0]
    assert first.ok is False and first.result == {"error": "earliest_start must be 24-hour 'HH:MM'."}
    assert result.trace[1].ok and result.trace[1].result["preferences_applied"]["earliest_start"] == "10:00"


async def test_f12_trailing_newline_in_latest_end_is_rejected():
    result = await run([
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, latest_end="15:00\n")]},
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, latest_end="15:00")]},
        {"content": "Option 1: SEC1001 + SEC2002."},
    ], "Plan CIS376 and CIS410, I'd like to finish early in the day.")
    assert result.stopped_reason == "answered" and result.answer_source != "system_error"
    assert result.trace[0].result == {"error": "latest_end must be 24-hour 'HH:MM'."}
    assert result.trace[1].ok


@pytest.mark.parametrize("value", ["00:00", "10:00", "23:59"])
async def test_f12_valid_times_are_still_accepted(value):
    result = await run([
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, earliest_start=value)]},
        {"content": "Option 1: SEC1001 + SEC2002."},
    ], "Plan CIS376 and CIS410, I'd like to start later in the day.")
    assert result.trace[0].ok
    assert result.trace[0].result["preferences_applied"]["earliest_start"] == value


async def test_f12_empty_time_still_means_no_limit():
    result = await run([
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, earliest_start="", latest_end=None)]},
        {"content": "Option 1: SEC1001 + SEC2002."},
    ], "Plan CIS376 and CIS410")
    assert result.trace[0].ok and result.trace[0].result["preferences_applied"]["earliest_start"] is None


# ---------------------------------------------------------------- F8


def _live_extractors() -> int:
    gc.collect()
    return sum(1 for o in gc.get_objects() if isinstance(o, constraints._Extractor))


def test_f8_extractor_is_freed_after_use():
    ex = constraints._Extractor("Plan CIS376, no classes before 10 and not on Fridays please")
    ex.parse("no classes before 10")
    ref = weakref.ref(ex)
    del ex
    gc.collect()
    assert ref() is None


def test_f8_no_request_text_is_kept_after_extract():
    before = _live_extractors()
    for i in range(50):
        constraints.extract(f"Plan CIS376, no classes before 10 and not on Fridays please, request {i}")
    assert _live_extractors() == before


async def test_f8_no_request_text_is_kept_after_a_run():
    before = _live_extractors()
    await run([
        {"tool_calls": [call("plan_schedule", course_ids=COURSES, earliest_start="10:00",
                             required_preferences=["earliest_start"])]},
        {"content": "CIS410 options: SEC2001 or SEC2002."},
    ], "Plan CIS376 and CIS410, no classes before 10 (secret marker 7f3a).")
    assert _live_extractors() == before
    gc.collect()
    assert not any("7f3a" in o.text for o in gc.get_objects() if isinstance(o, constraints._Extractor))


def test_f8_repeated_fragment_is_parsed_once_per_extractor():
    ex = constraints._Extractor("no classes before 10")
    first = ex.parse("no classes before 10")
    assert ex.parse("no classes before 10") is first
    other = constraints._Extractor("no classes before 10")
    assert other.parse("no classes before 10") is not first  # never shared between requests


def test_f8_readings_are_unchanged():
    r = constraints.extract("I can't do classes before 10am and no Fridays.")
    assert r["earliest_start"].value == "10:00" and r["earliest_start"].verdict == "required"
    assert r["avoid_days"].value == ("FRI",)
