"""Regression tests for the WS3 security audit of 2026-10-29, F2 (Phase B2).

F2  meeting days, meeting times and credit hours the answer gives for a
    planned section must be the ones in the plan_schedule result. A wrong
    detail gets one revision, then the fallback answer.

The rule tests use a hand-built plan_schedule result (mock data). The
end-to-end tests script the model; MCP, planner and validators are real
(in-process fake server, development data): for S10001, CIS410 has SEC2001
(MON/WED 10:30-11:45, in person) and SEC2002 (online), 3 credit hours each.
"""

import json
import time
from pathlib import Path

import pytest
from mcp import Client

from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.evidence import _course_credits, section_detail_claims
from agent.llm import ScriptedLLM, call
from dev.fake_mcp_server import server

TERM = "2027SP"
EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence"


def sec(sid, cid, meetings, modality="in_person"):
    return {"section_id": sid, "course_id": cid, "modality": modality, "seats_available": 5,
            "meetings": [{"days": d, "start": a, "end": b, "location": "Building A 101"} for d, a, b in meetings]}


S1001 = sec("SEC1001", "CIS376", [(["MON", "WED"], "09:30", "10:45")])
S2001 = sec("SEC2001", "CIS410", [(["MON", "WED"], "10:30", "11:45")])
S2002 = sec("SEC2002", "CIS410", [], "online")
S5302 = sec("SEC5302", "CIS360", [(["MON", "WED"], "18:00", "19:15")])
S5601 = sec("SEC5601", "CIS390", [(["MON", "WED"], "11:00", "12:15")])
TRACE = [{"tool": "plan_schedule", "ok": True,
          "arguments": {"course_ids": ["CIS376", "CIS410", "CIS360", "CIS390"]},
          "result": {"options": [
              {"section_ids": ["SEC1001", "SEC2002"], "total_credit_hours": 6, "sections": [S1001, S2002]},
              {"section_ids": ["SEC2001", "SEC5302", "SEC5601"], "total_credit_hours": 9,
               "sections": [S2001, S5302, S5601]}],
              "requested_sections": None, "current_registrations": []}}]
REQUEST = "I want classes between 9-5 please"

WRONG = {
    "audit repro": "SEC2002 meets FRI 07:00-08:00 in Building Z.",
    "wrong time": "SEC1001 meets Monday and Wednesday, 8:00 AM - 9:15 AM.",
    "wrong days": "SEC1001: Tuesday and Thursday, 9:30 AM - 10:45 AM.",
    "wrong day codes": "SEC1001 (TR 09:30-10:45)",
    "online section given a time": "CIS410 (SEC2002): Monday 1:00 PM - 2:15 PM",
    "AM instead of PM": "SEC5302 meets Mon/Wed 6:00 AM - 7:15 AM.",
    "meets on wrong day": "SEC2001 meets on Fridays.",
    "sub-item days": "- **CIS376 (SEC1001)**\n  - Days: Monday, Friday\n  - Time: 9:30 AM - 10:45 AM",
    "sub-item time": "1. **CIS376 (SEC1001)**\n   - Time: 9:00 AM - 10:15 AM",
    "wrong total": "Total credit hours: 7",
    "course named without a section": "CIS376: Monday and Wednesday, 1:00 PM - 2:15 PM",
    "credits above every option total": "SEC2002 is 12 credit hours.",
}

RIGHT = {
    "plain": "SEC1001 meets Monday and Wednesday from 9:30 AM to 10:45 AM in Building A 101.",
    "24-hour clock": "SEC5302 (MON, WED 18:00–19:15, Building B 210)",
    "shared meridiem": "SEC5302: Mondays and Wednesdays, 06:00–07:15 PM",
    "range across noon": "SEC5601 meets Monday and Wednesday from 11:00 AM to 12:15 PM.",
    "no meridiem": "SEC5302: Monday and Wednesday, 6:00 - 7:15",
    "a.m. with dots": "SEC1001 meets Monday and Wednesday, 9:30 a.m. to 10:45 a.m. in Building A 101.",
    "day codes": "SEC1001 (MW 9:30-10:45)",
    "online": "CIS410 (SEC2002): Online, no meetings. Total credit hours: 3.",
    "derived course credits": "CIS410 - SEC2002 (3 credits) and CIS376 - SEC1001 (3 credits)",
    "option total": "**Total Credit Hours:** 6",
    "a time that is not a range": "SEC2001 ends at 11:45, after your 11:00 limit.",
    "overlap span": "SEC1001 and SEC2001 overlap from 10:30 to 10:45 on Monday and Wednesday.",
    "student window": "SEC1001 fits inside the 9:00 AM - 5:00 PM window you asked for.",
    "two sections of one course": ("CIS410 has an in-person section (SEC2001) on Monday and Wednesday from "
                                   "10:30 AM to 11:45 AM and an online section (SEC2002)."),
    "free day": "SEC1001 meets Monday and Wednesday, so your Friday stays free.",
    "number range that is not a time": "Here are 2-3 options with SEC1001.",
    "course count": "You can take 3-4 courses; SEC1001 is one.",
    "credits with current registration": "With SEC1001 and SEC2002 you'll be at 6 credits, under your limit.",
}


@pytest.mark.parametrize("answer", WRONG.values(), ids=WRONG.keys())
def test_wrong_section_details_are_claims(answer):
    found = section_detail_claims(answer, TRACE, REQUEST)
    assert found and found[0]["details"]
    assert "plan_schedule result" in found[0]["reason"]


@pytest.mark.parametrize("answer", RIGHT.values(), ids=RIGHT.keys())
def test_correct_section_details_pass(answer):
    assert section_detail_claims(answer, TRACE, REQUEST) == []


def test_claim_names_the_wrong_detail_and_section():
    [found] = section_detail_claims("SEC1001 meets Monday and Wednesday, 8:00 AM - 9:15 AM.", TRACE)
    assert found["section_ids"] == ["SEC1001"]
    assert found["details"] == ["time 8:00 AM - 9:15 AM."]


def test_the_plans_time_window_is_not_a_section_time():
    trace = json.loads(json.dumps(TRACE))
    trace[0]["arguments"].update(earliest_start="10:00", latest_end="17:00")
    assert section_detail_claims("SEC2001 fits your 10:00-17:00 window.", trace) == []


def test_current_registrations_are_checked_by_course():
    trace = json.loads(json.dumps(TRACE))
    trace[0]["result"]["current_registrations"] = [
        {"course_id": "CIS330", "modality": "in_person", "meetings": [
            {"days": ["TUE", "THU"], "start": "13:00", "end": "14:15", "location": "Building C 1"}]}]
    assert section_detail_claims("You are registered in CIS330, Tuesday and Thursday 1:00 PM - 2:15 PM.", trace) == []
    assert section_detail_claims("You are registered in CIS330, Tuesday and Thursday 3:00 PM - 4:15 PM.", trace)


def test_without_a_plan_nothing_is_checked():
    assert section_detail_claims("SEC1001 meets Friday 7:00 AM - 8:00 AM.", []) == []
    failed = [{"tool": "plan_schedule", "ok": False, "arguments": {}, "result": {"error": "x"}}]
    assert section_detail_claims("SEC1001 meets Friday 7:00 AM - 8:00 AM.", failed) == []


def test_a_malformed_plan_result_does_not_raise():
    trace = [
        {"tool": "plan_schedule", "ok": True, "arguments": None, "result": None},
        {"tool": "plan_schedule", "ok": True, "arguments": {"course_ids": ["CIS376"]}, "result": {
            "options": [None, "x", {"total_credit_hours": "3", "sections": [None, {"section_id": "SEC1001"},
                        {"section_id": "SEC1001", "course_id": "CIS376",
                         "meetings": [None, {"days": None, "start": 930, "end": "10:45"},
                                      {"days": ["MON"], "start": "09:30", "end": "10:45"}]}]}],
            "current_registrations": [None, "x"],
            "requested_sections": {"sections": [], "issues": [None, {"message": None}, {"message": 7}]}}},
        {"tool": "search_courses", "ok": True, "result": {"courses": [None, {"course_id": "CIS376"}]}},
        {"tool": "get_my_record", "ok": True, "result": None},
    ]
    assert section_detail_claims("SEC1001 meets Monday 9:30 AM - 10:45 AM, 3 credit hours.", trace, "x") == []
    assert section_detail_claims("SEC1001 meets Friday 7:00 AM - 8:00 AM.", trace)


def _saved_record(path):
    record = json.loads((EVIDENCE / path).read_text(encoding="utf-8"))["record"]
    return record["request"], record["result"]["answer"], record["result"]["trace"]


def test_the_real_wrong_answer_from_the_audit_is_caught():
    # held-out run 1, H28: the plan says SEC5201 meets WED 17:00-18:50
    request, answer, trace = _saved_record("2026-10-19-heldout-run1/H28.json")
    [found] = section_detail_claims(answer, trace, request)
    assert found["details"] == ["time 5:00 PM – 7:50 PM"]
    assert section_detail_claims(answer.replace("7:50 PM", "6:50 PM"), trace, request) == []


@pytest.mark.parametrize("unit", [
    "SEC1001 meets Monday and Wednesday 9:30 AM - 10:45 AM, 3 credit hours. ",
    "SEC1001 overlaps 10:30 to 10:45 ",  # one line repeating an ID (took 26 s before IDs were de-duplicated)
    "SEC1001 Monday, Wednesday 9:30-10:45 ",
    # review R5: many ranges, then many day lists on one line (2.4 s at 45 KB before bisect)
    "SEC1001 " + "9:30-10:45 " * 2800 + "Monday " * 4100,
    # final review N1: repeated day labels on one line (33 s / 24 s before the bounded look-back)
    "SEC1001 " + "Days: Monday " * 5000,
    "SEC1001 " + "Avoided days: Friday " * 3000,
])
def test_a_long_answer_is_checked_in_linear_time(unit):
    answer = (unit * 3000)[:60000]
    start = time.perf_counter()
    assert section_detail_claims(answer, TRACE) == []
    assert time.perf_counter() - start < 5


# ------------------------------------------------------------ end to end

PLAN_CIS410 = {"tool_calls": [call("plan_schedule", course_ids=["CIS410"])]}
RIGHT_ANSWER = ("For CIS410 you can take the online section SEC2002 (3 credit hours). SEC2001 meets Monday and "
                "Wednesday from 10:30 AM to 11:45 AM, which conflicts with your current CIS376 section.")
WRONG_TIME = "SEC2001 meets Tuesday and Thursday from 1:00 PM to 2:15 PM."
WRONG_CREDITS = "SEC2002 is the online section of CIS410 and is 4 credit hours."


async def ask(request, responses, student="S10001"):
    llm = ScriptedLLM(responses)
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, student, TERM).run(request)
    return result, llm


@pytest.mark.anyio
@pytest.mark.parametrize("wrong", [WRONG_TIME, WRONG_CREDITS])
async def test_wrong_details_twice_get_the_fallback_answer(wrong):
    result, _ = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": wrong}, {"content": wrong}])
    assert result.answer_source == "system_fallback"
    assert result.blocked["reason"] == "unverified_after_revision"
    assert any("plan_schedule result" in c["reason"] for c in result.unsupported_claims)


@pytest.mark.anyio
async def test_wrong_details_are_revised_first():
    result, llm = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": WRONG_CREDITS}, {"content": RIGHT_ANSWER}])
    assert result.answer_source != "system_fallback"
    assert RIGHT_ANSWER in result.answer
    assert result.grounded and not result.unsupported_claims
    revise = [m for m in llm.received[2] if m["role"] == "user"][-1]["content"]
    assert WRONG_CREDITS in revise and "plan_schedule result" in revise


@pytest.mark.anyio
async def test_correct_details_pass_without_a_revision():
    result, llm = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": RIGHT_ANSWER}])
    assert result.answer_source != "system_fallback"
    assert RIGHT_ANSWER in result.answer
    assert result.grounded and not result.unsupported_claims
    assert len(llm.received) == 2


# ------------------------------------------------------------ pre-commit review (R1-R6)

def with_current(trace, course, days, start, end):
    trace = json.loads(json.dumps(trace))
    trace[0]["result"]["current_registrations"] = [{"course_id": course, "modality": "in_person", "meetings": [
        {"days": days, "start": start, "end": end, "location": "Building C 1"}]}]
    return trace


CUR = with_current(TRACE, "CIS330", ["MON", "WED"], "10:00", "11:15")


@pytest.mark.parametrize("answer", [
    # R1: the time of the current class a planned section conflicts with
    "SEC2001 conflicts with your current CIS330 class, which meets Monday and Wednesday 10:00 AM - 11:15 AM.",
    "SEC2001 (Monday and Wednesday 10:30 AM - 11:45 AM) overlaps your CIS330 class, Monday and Wednesday "
    "10:00 AM - 11:15 AM.",
    # several sections and courses in one sentence, all correct
    "SEC1001 (CIS376) meets Monday and Wednesday 9:30 AM - 10:45 AM and SEC5302 (CIS360) meets Monday and "
    "Wednesday 6:00 PM - 7:15 PM.",
])
def test_correct_details_of_several_sections_in_one_sentence_pass(answer):
    assert section_detail_claims(answer, CUR, REQUEST) == []


@pytest.mark.parametrize("answer", [
    "SEC2001 conflicts with your current CIS330 class, which meets Monday and Wednesday 1:00 PM - 2:15 PM.",
    "SEC1001 (CIS376) meets Monday and Wednesday 9:30 AM - 10:45 AM and SEC5302 (CIS360) meets Monday and "
    "Wednesday 8:00 PM - 9:15 PM.",
    "SEC1001 (CIS376) meets Tuesday and Thursday 9:30 AM - 10:45 AM and SEC5302 (CIS360) meets Monday and "
    "Wednesday 6:00 PM - 7:15 PM.",
    # a sibling section's time given to the online section of the same course
    "CIS410 (SEC2002): Monday and Wednesday 10:30 AM - 11:45 AM",
    "CIS376 and CIS390 both meet Monday and Wednesday 2:00 PM - 3:15 PM.",
])
def test_a_wrong_detail_among_several_sections_is_still_caught(answer):
    assert section_detail_claims(answer, CUR, REQUEST)


@pytest.mark.parametrize("answer", [
    # R2: a line or sentence without IDs that is not a section detail
    "- SEC1001 (CIS376): Monday and Wednesday 9:30 AM - 10:45 AM\n- Lunch is free from 12:00 PM - 1:00 PM",
    "SEC1001 meets Monday and Wednesday 9:30 AM - 10:45 AM. Your lunch break stays free from 12:00 PM - 1:00 PM.",
    # R4: a preference label under a section
    "- SEC1001 (CIS376)\n  - Avoided days: Friday",
    "- SEC1001 (CIS376)\n  - Preferred days: Tuesday",
])
def test_text_that_only_follows_a_section_is_not_a_section_detail(answer):
    assert section_detail_claims(answer, TRACE, REQUEST) == []


@pytest.mark.parametrize("answer", [
    "- **CIS376 (SEC1001)**\n  - 9:00 AM - 10:15 AM",
    "- **CIS376 (SEC1001)**\n  - Monday, Friday 9:30 AM - 10:45 AM",
    "- **CIS376 (SEC1001)**\n  - **Time:** 9:00 AM - 10:15 AM",
    "SEC1001 (CIS376). Meets Monday and Wednesday 8:00 AM - 9:15 AM.",
    "- **CIS376 (SEC1001)** - Days: Monday, Friday",
    "- **CIS376 (SEC1001)**\n  - Meeting days: Friday",
])
def test_section_details_under_a_section_line_are_still_checked(answer):
    assert section_detail_claims(answer, TRACE, REQUEST)


def credit_trace():
    # course credits known from search_courses; option 1 brings the student to 10 of 18
    trace = json.loads(json.dumps(TRACE))
    trace[0]["result"]["options"][0]["current_registration"] = {"credit_hours_with_current": 10, "credit_limit": 18}
    rows = [{"course_id": c, "credit_hours": 3} for c in ("CIS376", "CIS410", "CIS360", "CIS390")]
    return [{"tool": "search_courses", "ok": True, "arguments": {}, "result": rows}] + trace


@pytest.mark.parametrize("answer", [
    # R3: numbers that follow from the plan's credit fields
    "With SEC1001 and SEC2002 you would still have 8 credit hours left before the limit.",
    "You are currently registered for 4 credit hours, so SEC1001 and SEC2002 bring you to 10 credit hours.",
    "SEC1001 and SEC2002 leave 12 credits of room under the 18 credit limit.",
])
def test_credit_arithmetic_from_the_plan_passes(answer):
    assert section_detail_claims(answer, credit_trace(), "") == []


@pytest.mark.parametrize("answer", [
    "SEC1001 and SEC2002 bring you to 11 credit hours.",
    "SEC1001 is 4 credit hours.",
    "Total credit hours: 7",
])
def test_wrong_credit_numbers_are_still_caught(answer):
    assert section_detail_claims(answer, credit_trace(), "")


def opt(total, *courses):
    return {"total_credit_hours": total, "sections": [{"course_id": c} for c in courses]}


def plan_of(*options):
    return [{"tool": "plan_schedule", "ok": True, "arguments": {}, "result": {"options": list(options)}}]


def test_course_credits_are_derived_from_option_totals():
    assert _course_credits(plan_of(opt(3, "A"), opt(7, "A", "B"), opt(10, "A", "B", "C"))) == {"A": 3, "B": 4, "C": 3}
    assert _course_credits(plan_of(opt(6, "A", "B"), opt(3, "A"))) == {"A": 3, "B": 3}


def test_contradictory_credit_data_derives_no_impossible_value():
    search = [{"tool": "search_courses", "ok": True, "arguments": {}, "result": [{"course_id": "A", "credit_hours": 4}]}]
    assert _course_credits(search + plan_of(opt(3, "A", "B"))) == {"A": 4}


def test_unexpected_data_shapes_do_not_raise():
    # R6: shapes the planner does not produce today are skipped, not fatal
    trace = json.loads(json.dumps(TRACE))
    trace[0]["result"]["requested_sections"] = {"sections": {"x": 1}, "issues": {"x": 1}, "registration_issues": "x"}
    trace[0]["result"]["options"][1]["sections"][1]["meetings"][0]["days"] = "MON"
    trace.append({"tool": "plan_schedule", "ok": True, "result": TRACE[0]["result"]})  # no "arguments"
    trace.append({"tool": "get_my_record", "ok": True})  # no "result"
    assert section_detail_claims("SEC5302 meets Monday 6:00 PM - 7:15 PM.", trace, "x") == []
    assert section_detail_claims("SEC1001 meets Friday 7:00 AM - 8:00 AM.", trace, "x")


# ------------------------------------------------------------ final review (N2, N4)

@pytest.mark.parametrize("answer", [
    # N2: a course's own credit hours, stated for that one course (all courses are 3 credits)
    "CIS410 (SEC2002) is 6 credit hours.",
    "CIS376 is 18 credit hours.",
    "CIS410 (6 credits)",
    "SEC2002 (CIS410, 9 credits)",
    "CIS410 - SEC2002 (9 credits)",
    "SEC1001 is a 6-credit section.",
    "- **CIS376 (SEC1001)**\n  - Credits: 6",
])
def test_a_wrong_credit_number_for_one_course_is_caught(answer):
    assert section_detail_claims(answer, credit_trace(), "")


@pytest.mark.parametrize("answer", [
    "CIS410 is 3 credits.",
    "CIS410 (3 credits)",
    "SEC2002 (CIS410, 3 credits)",
    "CIS410 - SEC2002 (3 credit hours)",
    "- **CIS376 (SEC1001)**\n  - Credits: 3",
    # schedule totals and remaining credits are not one course's credit hours
    "SEC1001 and SEC2002 (6 credits)",
    "SEC1001 and SEC2002 total 6 credit hours.",
    "Option 1 (SEC1001, SEC2002): 6 credits",
    "- **Option 1: SEC1001, SEC2002**\n  - Credits: 6",
    "CIS410 brings you to 10 credit hours.",
    "CIS410 is 3 credits, so the option is 6 credit hours in total.",
    "With CIS410 you would still have 8 credit hours left under the limit.",
    "CIS410 is 12 credits under your limit with this option.",
])
def test_course_credits_totals_and_remaining_credits_pass(answer):
    assert section_detail_claims(answer, credit_trace(), "") == []


@pytest.mark.parametrize("answer", [
    # release gate: a word elsewhere in the sentence must not excuse a wrong course credit number
    "SEC2002 is 4 credit hours and has seats available.",
    "SEC2002 is 4 credit hours, and registration is available now.",
    "CIS410 (SEC2002) is 6 credit hours and the section is already open.",
    "SEC2002 is 12 credit hours, so it fits under your limit.",
    "SEC2002 is 8 credit hours with no meetings left to schedule.",
    "CIS410 (SEC2002) is 9 credit hours, which keeps your total low.",
    "SEC2002 is 4 credit hours and has more open seats than SEC2001.",
])
def test_unrelated_words_do_not_excuse_a_wrong_course_credit(answer):
    assert section_detail_claims(answer, credit_trace(), "")


@pytest.mark.parametrize("answer", [
    "You have 12 credits left.",
    "With SEC2002 you have 12 credits left.",
    "SEC2002 leaves you 8 credit hours remaining.",
    "You are currently registered for 4 credit hours.",
    "SEC2002 is 3 credit hours and has seats available.",
    "CIS410 (SEC2002): 3 credit hours, seats available.",
    "SEC1001 and SEC2002 give you 6 credit hours in total.",
    "SEC2002 brings your total to 10 credit hours.",
])
def test_arithmetic_tied_to_the_number_still_passes(answer):
    assert section_detail_claims(answer, credit_trace(), "") == []


def test_course_credits_are_not_checked_per_course_when_unknown():
    # TRACE has no search_courses rows and no one-course option: CIS410's credit hours are unknown
    assert section_detail_claims("CIS410 is 6 credit hours.", TRACE, "") == []


def test_malformed_course_ids_do_not_raise():
    # N4: course_id values that are not strings are skipped
    trace = credit_trace()
    trace[0]["result"].append({"course_id": ["CIS410"], "credit_hours": 4})
    trace[0]["result"].append({"course_id": {"x": 1}, "credit_hours": 4})
    trace[1]["result"]["options"][0]["sections"].append({"section_id": "SEC9", "course_id": ["CIS999"]})
    trace[1]["result"]["current_registrations"] = [{"course_id": 7, "meetings": []}]
    assert section_detail_claims("SEC1001 meets Monday 9:30 AM - 10:45 AM, 3 credit hours.", trace, "") == []
    assert section_detail_claims("SEC1001 meets Friday 7:00 AM - 8:00 AM.", trace, "")


CONFLICT_ANSWER = ("SEC2002 is the online section of CIS410 (3 credit hours). SEC2001 meets Monday and Wednesday "
                   "10:30 AM - 11:45 AM, which conflicts with your current CIS376 section on Monday and Wednesday "
                   "9:30 AM - 10:45 AM.")
CREDITS_LEFT_ANSWER = ("For CIS410 you can take the online section SEC2002. It brings you to 6 credit hours, so you "
                       "would still have 12 credit hours left under your limit.")


@pytest.mark.anyio
@pytest.mark.parametrize("answer", [CONFLICT_ANSWER, CREDITS_LEFT_ANSWER])
async def test_correct_answers_get_no_revision_and_no_fallback(answer):
    # real fake-server data: S10001 is registered in CIS376 (MON/WED 09:30-10:45), 6 of 18 credit hours with CIS410
    result, llm = await ask("Plan CIS410 for me", [PLAN_CIS410, {"content": answer}, {"content": answer}])
    assert result.answer_source != "system_fallback"
    assert answer in result.answer
    assert not result.unsupported_claims
    assert len(llm.received) == 2
