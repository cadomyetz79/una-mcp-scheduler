"""Regression tests for the Workstream 3 quality pass (branch
fix/ws3-quality-pass), on top of tests/test_integration_readiness.py.

1. Current registrations: an option that needs a change to the student's
   current registrations is never presented as one the student can simply
   add; options that fit are kept apart from options that need a change.
   Options are still never removed (open team decision).
2. Hard constraints: negation, exceptions, ambiguous times, mixed hard and
   soft wishes; an uncertain mandatory limit is never silently ignored.
3. R7: dev/chat.py and dev/demo_plan.py select the data directory and pass it
   to the MCP subprocess.
4. R9: per-request model timing statistics under concurrency.
"""

import asyncio
import json
from pathlib import Path

import pytest
from mcp import Client

from agent import constraints
from agent.assistant import SchedulingAssistant
from agent.banner_tools import BackendUnavailable, BannerTools
from agent.evidence import NOT_CHECKED_NOTE, registration_claims, registration_notes
from agent.llm import ScriptedLLM, call
from agent.planner import plan_schedules
from dev.fake_mcp_server import server
from evaluation.run_eval import DEV_REGISTRATION_ORACLES, load_cases
from scheduling.models import Course, Section, Student

pytestmark = pytest.mark.anyio

TERM = "2027SP"
ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ 1. current registrations

def section(sid, cid, days, start="09:00", end="10:00"):
    return Section.from_dict({"section_id": sid, "course_id": cid, "term_id": TERM, "section_number": "01",
                              "modality": "in_person", "capacity": 10, "enrolled_count": 0,
                              "meetings": [{"days": days, "start_time": start, "end_time": end, "location": "X"}]})


class Tools:
    """Planner-level stub. The student (limit 9) is registered in CUR-1
    (CCC100, Wed 09:00-10:00, 3 credits)."""

    def __init__(self, current=("CUR",), limit=9, credits_readable=True, listable=True):
        self.student_ = Student.from_dict({"student_id": "S1", "program": "IT", "max_credit_hours": limit,
                                           "active": True}, [])
        self.courses = {c: Course.from_dict({"course_id": c, "title": c, "credit_hours": 3, "prerequisites": [],
                                             "corequisites": []}) for c in ("AAA100", "BBB100", "CCC100")}
        self.secs = {
            "AAA100": [section("A-MON", "AAA100", ["MON"]), section("A-WED", "AAA100", ["WED"])],
            "BBB100": [section("B-TUE", "BBB100", ["TUE"])],
            "CCC100": [section("CUR-1", "CCC100", ["WED"]), section("CUR-2", "CCC100", ["THU"])],
        }
        self.current = [self.secs["CCC100"][0]] if current else []
        self.credits_readable, self.listable = credits_readable, listable

    async def student(self, sid):
        return self.student_

    async def course(self, cid):
        if cid == "CCC100" and not self.credits_readable:
            raise BackendUnavailable("down", tool="get_course")
        return self.courses[cid]

    async def sections(self, cid, term):
        return self.secs.get(cid, [])

    async def enrollments(self, sid, term):
        return self.current if self.listable else None


def by_ids(plan):
    return {tuple(o["section_ids"]): o for o in plan.options}


async def test_each_option_says_how_it_fits_current_registrations():
    plan = await plan_schedules(Tools(), "S1", TERM, ["AAA100", "CCC100"])
    options = by_ids(plan)
    # keeping the section the student is already in is no change
    assert options[("A-MON", "CUR-1")]["registration_fit"] == "fits_current_registration"
    assert options[("A-MON", "CUR-1")]["current_registration"]["keeps_current_sections"] == ["CUR-1"]
    # another section of a registered course is a switch
    assert options[("A-MON", "CUR-2")]["registration_fit"] == "requires_registration_change"
    assert options[("A-MON", "CUR-2")]["current_registration"]["switches_section_of"] == ["CCC100"]
    # A-WED overlaps the current Wednesday class
    assert options[("A-WED", "CUR-2")]["current_registration"]["conflicts"][0]["current_course_id"] == "CCC100"
    # compatible options first; options are never removed
    assert [o["registration_fit"] for o in plan.options][0] == "fits_current_registration"
    assert len(plan.options) == 3


async def test_credit_limit_with_current_classes_needs_a_change():
    plan = await plan_schedules(Tools(limit=6), "S1", TERM, ["AAA100", "BBB100"])
    for option in plan.options:
        assert option["current_registration"]["credit_hours_with_current"] == 9
        assert option["registration_fit"] == "requires_registration_change"
        assert option["compatible_with_current_registration"] is False


async def test_unreadable_current_credits_are_not_confirmed_never_assumed_fine():
    plan = await plan_schedules(Tools(credits_readable=False), "S1", TERM, ["AAA100"])
    fits = {tuple(o["section_ids"]): (o["registration_fit"], o["compatible_with_current_registration"])
            for o in plan.options}
    assert fits[("A-MON",)] == ("not_confirmed", None)
    assert fits[("A-WED",)] == ("requires_registration_change", False)  # the overlap is known anyway


async def test_registrations_that_cannot_be_listed_mark_every_option_not_checked():
    plan = await plan_schedules(Tools(listable=False), "S1", TERM, ["AAA100"])
    assert plan.current_registrations_checked is False
    assert {o["registration_fit"] for o in plan.options} == {"not_checked"}
    assert all("compatible_with_current_registration" not in o for o in plan.options)


@pytest.mark.parametrize("named,limit,codes,fits", [
    (["A-MON"], 9, [], True),
    (["CUR-2"], 9, ["SWITCHES_CURRENT_SECTION"], False),
    (["A-WED"], 9, ["CONFLICTS_WITH_CURRENT_REGISTRATION"], False),
    (["A-MON", "B-TUE"], 6, ["CREDIT_LIMIT_WITH_CURRENT"], False),
])
async def test_named_sections_report_fit_apart_from_academic_validity(named, limit, codes, fits):
    courses = sorted({{"A": "AAA100", "B": "BBB100", "CUR": "CCC100"}[s.split("-")[0]] for s in named})
    plan = await plan_schedules(Tools(limit=limit), "S1", TERM, courses, requested_sections=named)
    rs = plan.requested_sections
    assert rs["valid_together"] is True  # academically valid either way
    assert [i["code"] for i in rs["registration_issues"]] == codes
    assert rs["fits_current_registration"] is fits


async def test_named_sections_without_a_registration_list_are_not_confirmed():
    plan = await plan_schedules(Tools(listable=False), "S1", TERM, ["AAA100"], requested_sections=["A-MON"])
    assert plan.requested_sections["fits_current_registration"] is None


def plan_trace(options, checked=True, current=None, requested=None):
    result = {"options": options, "current_registrations_checked": checked, "excluded": [],
              "current_registrations": current or [], "already_registered": [], "requested": ["AAA100"]}
    if requested:
        result["requested_sections"] = requested
    return [{"tool": "plan_schedule", "arguments": {}, "ok": True, "result": result}]


FIT = {"section_ids": ["A-MON"], "sections": [], "compatible_with_current_registration": True,
       "registration_fit": "fits_current_registration", "current_registration": {}}
CHANGE = {"section_ids": ["A-WED"], "sections": [], "compatible_with_current_registration": False,
          "registration_fit": "requires_registration_change",
          "current_registration": {"conflicts": [{"section_id": "A-WED", "course_id": "AAA100",
                                                  "current_course_id": "CCC100"}], "switches_section_of": []}}
UNSURE = {"section_ids": ["B-TUE"], "sections": [], "compatible_with_current_registration": None,
          "registration_fit": "not_confirmed", "current_registration": {}}


@pytest.mark.parametrize("answer,flagged", [
    ("You can take A-WED or A-MON.", ["A-WED"]),
    ("Both A-WED and A-MON fit your current schedule.", ["A-WED"]),
    ("A-WED fits your current schedule, no conflicts.", ["A-WED"]),
    ("A-WED doesn't overlap anything you're registered for.", ["A-WED"]),
    ("A-MON fits. A-WED overlaps your current CCC100 class.", []),
    ("A-WED doesn't fit with your current classes.", []),
    ("Taking A-WED would mean changing your current registration.", []),
    ("You can't take A-WED because of your CCC100 class.", []),
    ("All of these options fit with your current registrations.", [[]]),
])
def test_an_option_needing_a_change_is_never_presented_as_safe(answer, flagged):
    for s in ("A-MON", "A-WED", "B-TUE"):  # the stub IDs stand in for SEC IDs below
        answer = answer.replace(s, {"A-MON": "SEC9001", "A-WED": "SEC9002", "B-TUE": "SEC9003"}[s])
    trace = plan_trace([{**FIT, "section_ids": ["SEC9001"]}, {**CHANGE, "section_ids": ["SEC9002"]}])
    got = [c["section_ids"] for c in registration_claims(answer, trace)]
    expected = [["SEC9002"] if f == "A-WED" else [] for f in flagged] if flagged != [[]] else [[]]
    assert got == expected


def test_unchecked_or_unconfirmed_options_are_never_said_to_fit():
    unchecked = plan_trace([{"section_ids": ["SEC9001"], "sections": [], "registration_fit": "not_checked"}],
                           checked=False)
    assert registration_claims("SEC9001 fits with your current classes.", unchecked)
    assert registration_claims("SEC9001 is open.", unchecked) == []  # the fixed note covers it
    assert registration_notes(unchecked) == [NOT_CHECKED_NOTE]
    unsure = plan_trace([{**UNSURE, "section_ids": ["SEC9003"]}])
    assert registration_claims("SEC9003 works with your registered classes.", unsure)
    assert any("couldn't confirm" in n for n in registration_notes(unsure))


def test_notes_keep_fitting_options_apart_from_options_needing_a_change():
    current = [{"course_id": "CCC100", "meetings": [{"days": ["WED"], "start": "09:00", "end": "10:00"}]}]
    notes = registration_notes(plan_trace([{**FIT, "section_ids": ["SEC9001"]},
                                           {**CHANGE, "section_ids": ["SEC9002"]}], current=current))
    assert notes[0] == "Note: these options fit with the classes you're already registered for: SEC9001."
    assert notes[1].startswith("Note: SEC9002 would require changing your current registration: ")
    assert "overlaps your current CCC100 class, WED 09:00-10:00" in notes[1]
    only_change = registration_notes(plan_trace([{**CHANGE, "section_ids": ["SEC9002"]}], current=current))
    assert only_change[0].startswith("Note: none of these options fits")


async def run_assistant(responses, request="Plan CIS410 for me.", student="S10001"):
    llm = ScriptedLLM(responses)
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, student, TERM).run(request)
    return result, llm


PLAN_410 = {"tool_calls": [call("plan_schedule", course_ids=["CIS410"])]}


async def test_assistant_replaces_an_answer_that_hides_a_needed_change():
    # S10001 is registered in SEC1001 (CIS376, MON/WED 09:30-10:45); SEC2001 overlaps it.
    result, llm = await run_assistant([PLAN_410, {"content": "You can take SEC2001 or SEC2002."},
                                       {"content": "Both SEC2001 and SEC2002 fit your current schedule."}])
    assert result.answer_source == "system_fallback"
    assert result.registration_claims and result.blocked["reason"] == "unverified_after_revision"
    lines = result.answer.splitlines()
    assert any(line.startswith("- SEC2002") and "fits with the classes you're already registered for" in line
               for line in lines)
    assert any(line.startswith("- SEC2001") and "requires changing your current registration" in line
               for line in lines)
    assert "SEC1001" not in result.answer  # current sections are described by course and time
    summary = result.trace[0].result["registration_summary"]
    assert summary["fits_current_registration"] == [["SEC2002"]]
    assert summary["requires_registration_change"] == [["SEC2001"]]


async def test_a_corrected_answer_is_kept_with_both_groups_noted():
    result, _ = await run_assistant([PLAN_410, {"content": "SEC2001 and SEC2002 both work."},
                                     {"content": "SEC2002 fits. SEC2001 overlaps your current CIS376 class."}])
    assert result.answer_source == "model+system_note" and result.grounded
    assert "Note: these options fit with the classes you're already registered for: SEC2002." in result.answer
    assert "Note: SEC2001 would require changing your current registration" in result.answer


async def test_yes_to_a_named_section_that_needs_a_change_is_not_accepted():
    result, _ = await run_assistant([PLAN_410, {"content": "Yes."}, {"content": "Yes."}],
                                    request="Can I take SEC2001 for CIS410?")
    assert result.answer_source == "system_fallback"
    assert "SEC2001 (CIS410) overlaps your current CIS376 class" in result.answer


def test_dev_oracle_answers_state_registration_changes_and_nothing_else_changed():
    overlay = json.loads(DEV_REGISTRATION_ORACLES.read_text(encoding="utf-8"))
    original = {c["id"]: c for c in json.loads((ROOT / "evaluation" / "cases.json").read_text())["cases"]}
    loaded = {c["id"]: c for c in load_cases(dataset="dev", scoring_version=1)["cases"]}
    for cid, answer in overlay["oracle_answer"].items():
        assert "overlaps your current CIS376 class" in answer
        assert loaded[cid]["oracle"][-1] == {"content": answer}
        assert loaded[cid]["oracle"][:-1] == original[cid]["oracle"][:-1]  # same tool calls
        assert loaded[cid]["expect"] == original[cid]["expect"]  # same expectations


# ------------------------------------------------------------------ 2. hard constraints

def reading(text):
    return {p: r for p, r in constraints.extract(text).items() if r.mentioned}


READ = [
    # negation
    ("Fridays aren't a problem, but I can't do Mondays.", {"avoid_days": (("MON",), "required")}),
    ("I don't need to avoid Fridays.", {"avoid_days": ((), "soft")}),
    ("Fridays are not okay for me.", {"avoid_days": (("FRI",), "required")}),
    ("I can't do anything before 10 or after 4.", {"earliest_start": ("10:00", "required"),
                                                    "latest_end": ("16:00", "required")}),
    ("I'm not free until 11, that's a must.", {"earliest_start": ("11:00", "required")}),
    ("I don't want to finish later than 4.", {"latest_end": ("16:00", "unknown")}),
    ("No problem with Fridays, but nothing after 5pm at all.", {"avoid_days": ((), "unknown"),
                                                                "latest_end": ("17:00", "required")}),
    ("I can't do Fridays or anything before 10am.", {"earliest_start": ("10:00", "required"),
                                                     "avoid_days": (("FRI",), "required")}),
    # exceptions
    ("Any day except Friday works for me.", {"avoid_days": (("FRI",), "unknown")}),
    ("No classes before 10am, not on Fridays either.", {"earliest_start": ("10:00", "unknown"),
                                                        "avoid_days": (("FRI",), "unknown")}),
    # ambiguous or unusual time wording that can still be read exactly
    ("I must be done by 10 at night.", {"latest_end": ("22:00", "required")}),
    ("I can't do anything before 8 in the morning.", {"earliest_start": ("08:00", "required")}),
    ("I can't start before 9.30, that's a must.", {"earliest_start": ("09:30", "required")}),
    ("I must finish by 5:30 p.m. at the latest.", {"latest_end": ("17:30", "required")}),
    ("I can only take classes 10am-3pm.", {"earliest_start": ("10:00", "unknown"),
                                           "latest_end": ("15:00", "unknown")}),
    # mixed hard and soft: the mandatory limit decides, the wish next to it is reported
    ("I must be done by 5pm, ideally by 3pm.", {"latest_end": ("17:00", "required")}),
    ("I can't do Fridays. Ideally no Mondays either.", {"avoid_days": (("FRI",), "required")}),
    ("I absolutely can't start before 9, and I'd prefer to start after 10.",
     {"earliest_start": ("09:00", "required")}),
    ("I can't do Fridays, and ideally nothing before 10am.", {"avoid_days": (("FRI",), "required"),
                                                              "earliest_start": ("10:00", "soft")}),
    ("Nothing past 6 at all, though finishing by 4 would be nice.", {"latest_end": ("18:00", "required")}),
    # relaxed limits stay "conflicting": never enforced as mandatory
    ("I can't do Fridays. Actually Fridays aren't a problem.", {"avoid_days": (("FRI",), "conflicting")}),
    ("I must avoid Wednesdays. Actually, Wednesdays are fine if there's no other way.",
     {"avoid_days": (("WED",), "conflicting")}),
]


@pytest.mark.parametrize("text,expected", READ)
def test_hard_constraint_reading(text, expected):
    got = {p: (r.value, r.verdict) for p, r in reading(text).items() if r.reliable}
    assert got == expected
    assert constraints.clarifications(text) == []


@pytest.mark.parametrize("text,soft", [
    ("I must be done by 5pm, ideally by 3pm.", {"latest_end": ("15:00",)}),
    ("I can't do Fridays. Ideally no Mondays either.", {"avoid_days": ("MON",)}),
    ("I absolutely can't start before 9, and I'd prefer to start after 10.", {"earliest_start": ("10:00",)}),
])
def test_a_wish_next_to_a_mandatory_limit_is_reported_not_merged(text, soft):
    assert {p: r.soft_unapplied for p, r in reading(text).items() if r.soft_unapplied} == soft
    res = constraints.resolve(text, None, None, [], [])
    [note] = [c for c in res.changes if "soft_wish_not_applied" in c]
    assert note["soft_wish_not_applied"] == list(next(iter(soft.values())))


@pytest.mark.parametrize("text,pref,kind", [
    ("I can't have anything after 10.", "latest_end", "ampm"),
    ("I must start around 10.", "earliest_start", "approximate"),
    ("I can't start before 9 or 10.", "earliest_start", "alternatives"),
    ("I must finish by 4ish.", "latest_end", "vague"),
    ("I can't do mornings.", "earliest_start", "vague"),
    ("No classes before 10, except on Tuesdays, that's a must.", "earliest_start", "partial_day"),
    ("I can't stay past 3pm on Fridays.", "latest_end", "partial_day"),
    ("I can't do anything after 3pm, except on Mondays.", "latest_end", "partial_day"),
    ("I'm free all day except 12-1, that's a must.", "earliest_start", "busy_range"),
    ("Avoid Fridays if you can, but Mondays are a must.", "avoid_days", "days"),
])
def test_an_uncertain_mandatory_limit_is_asked_about(text, pref, kind):
    items = {i["preference"]: i["kind"] for i in constraints.clarifications(text)}
    assert items.get(pref) == kind
    assert constraints.system_arguments(text) is None


@pytest.mark.parametrize("text", [
    "Fridays are fine except after 3pm.",           # a wish, not a limit: the model's reading stands
    "Plan CIS340, ideally not too early.",
    "Schedule CIS360 on 2027-01-15 at 6:00 PM in room 101.",
])
def test_uncertain_wishes_are_not_turned_into_limits(text):
    assert constraints.clarifications(text) == []
    assert not any(r.reliable and r.value for r in reading(text).values())


@pytest.fixture
def heldout_data(monkeypatch):
    import dev.fake_mcp_server as fake
    monkeypatch.setattr(fake, "DATA_DIR", ROOT / "evaluation" / "heldout" / "data")  # development data


def plan_of(result):
    return next(t.result for t in result.trace if t.tool == "plan_schedule" and t.ok)


async def test_a_mandatory_limit_beats_the_wish_the_model_passed(heldout_data):
    # CIS340 + CIS360 for S20002; SEC5302 (CIS360) ends 19:15
    result, _ = await run_assistant([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS340", "CIS360"], latest_end="15:00")]},
        {"content": "Here are your options."}], request="I must be done by 5pm, ideally by 3pm. Plan CIS340 and "
                                                        "CIS360.", student="S20002")
    plan = plan_of(result)
    assert plan["preferences_applied"]["latest_end"] == "17:00"
    assert plan["preferences_applied"]["required"] == ["latest_end"]
    assert any(c.get("soft_wish_not_applied") == ["15:00"] for c in plan["constraint_changes"])
    assert plan["options"] and all(m["end"] <= "17:00" for o in plan["options"] for s in o["sections"]
                                   for m in s["meetings"])


async def test_a_mandatory_day_next_to_a_wish_is_enforced_when_the_model_omits_it(heldout_data):
    result, _ = await run_assistant([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS340", "CIS360"])]},
        {"content": "Here are your options."}], request="I can't do Fridays. Ideally no Mondays either. Plan CIS340 "
                                                        "and CIS360.", student="S20002")
    plan = plan_of(result)
    assert plan["preferences_applied"]["avoid_days"] == ["FRI"]
    assert plan["preferences_applied"]["required"] == ["avoid_days"]
    assert all("FRI" not in m["days"] for o in plan["options"] for s in o["sections"] for m in s["meetings"])


async def test_an_unclear_mandatory_part_stops_planning(heldout_data):
    result, _ = await run_assistant([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS340"], avoid_days=["FRI"])]},
        {"content": "unused"}], request="Avoid Fridays if you can, but Mondays are a must. Plan CIS340.",
        student="S20002")
    assert result.answer_source == "system_clarification" and result.mcp_calls == []
    assert "Which days do you need to keep completely free" in result.answer


# ------------------------------------------------------------------ 3. R7: data directory for the dev tools

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from dev.stdio_server import DEFAULT_DATA_DIR, DataDirError, resolve_data_dir, server_params  # noqa: E402


@pytest.fixture
def custom_data(tmp_path):
    """A copy of data/ in which S10001's credit limit is 12 and SEC2001 is gone."""
    shutil.copytree(DEFAULT_DATA_DIR, tmp_path / "data")
    d = tmp_path / "data"
    students = json.loads((d / "students.json").read_text())
    for s in students:
        if s["student_id"] == "S10001":
            s["max_credit_hours"] = 12
    (d / "students.json").write_text(json.dumps(students))
    sections = [s for s in json.loads((d / "sections.json").read_text()) if s["section_id"] != "SEC2001"]
    (d / "sections.json").write_text(json.dumps(sections))
    return d


def test_data_dir_choice_flag_then_environment_then_default(custom_data, tmp_path):
    assert resolve_data_dir(str(custom_data), environ={}) == custom_data.resolve()
    assert resolve_data_dir(None, environ={"UNA_DATA_DIR": str(custom_data)}) == custom_data.resolve()
    assert resolve_data_dir(str(custom_data), environ={"UNA_DATA_DIR": "/elsewhere"}) == custom_data.resolve()
    assert resolve_data_dir(None, environ={}) == DEFAULT_DATA_DIR
    with pytest.raises(DataDirError, match="not found"):
        resolve_data_dir(str(tmp_path / "nope"), environ={})
    (tmp_path / "partial").mkdir()
    (tmp_path / "partial" / "students.json").write_text("[]")
    with pytest.raises(DataDirError, match="missing: course_history.json, courses.json, sections.json"):
        resolve_data_dir(str(tmp_path / "partial"), environ={})


def test_only_the_data_directory_is_added_to_the_server_environment(custom_data):
    params = server_params(custom_data)
    assert params.env == {"UNA_DATA_DIR": str(custom_data)}  # the rest of the shell is not passed on


async def test_the_stdio_server_reads_the_chosen_directory(custom_data):
    async with Client(server_params(custom_data)) as client:
        student = await BannerTools(client).student("S10001")
        sections = await BannerTools(client).sections("CIS410", TERM)
    assert student.max_credit_hours == 12
    assert [s.section_id for s in sections] == ["SEC2002"]


def run_dev(script, *args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "UNA_DATA_DIR"} | (env_extra or {})
    return subprocess.run([sys.executable, str(ROOT / "dev" / script), *args], capture_output=True, text=True,
                          cwd=ROOT, env=env, timeout=120)


@pytest.mark.parametrize("how", ["flag", "environment"])
def test_demo_plan_uses_the_chosen_data(custom_data, how):
    args, env = (["--data-dir", str(custom_data)], None) if how == "flag" else ([], {"UNA_DATA_DIR": str(custom_data)})
    done = run_dev("demo_plan.py", "S10001", TERM, "CIS410", *args, env_extra=env)
    assert done.returncode == 0, done.stderr[-500:]
    out = json.loads(done.stdout)
    assert out["data_dir"] == str(custom_data.resolve())
    assert [o["section_ids"] for o in out["plan"]["options"]] == [["SEC2002"]]


def test_chat_refuses_a_bad_data_directory_before_starting(tmp_path):
    done = run_dev("chat.py", "--data-dir", str(tmp_path / "missing"), "Plan CIS410")
    assert done.returncode == 2 and "data directory not found" in done.stderr


# ------------------------------------------------------------------ 4. R9: per-request model statistics

import time as _time  # noqa: E402

from agent.llm import OllamaLLM, call_log  # noqa: E402
from evaluation.run_eval import run_case  # noqa: E402


def fake_ollama(script):
    """A stand-in for OllamaLLM._post: replies by request text, after a delay;
    eval_count marks which request (and which step) a record belongs to."""
    def post(payload):
        request = next(m["content"] for m in payload["messages"] if m["role"] == "user")
        key = next(k for k in script if k in request)
        steps, delay, marker = script[key]
        step = sum(1 for m in payload["messages"] if m["role"] == "tool") and 1
        _time.sleep(delay)
        return {"message": steps[step], "eval_count": marker * 10 + step, "prompt_eval_count": 1,
                "done_reason": "stop"}
    return post


def plan_reply(*courses):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "plan_schedule", "arguments": {"course_ids": list(courses)}}}]}


SCRIPT = {
    "Plan CIS410": ([plan_reply("CIS410"), {"role": "assistant",
                     "content": "SEC2002 fits. SEC2001 overlaps your current CIS376 class."}], 0.15, 1),
    "Plan CIS450": ([plan_reply("CIS450"), {"role": "assistant", "content": "Here is what I found."}], 0.01, 2),
}


async def test_concurrent_model_calls_keep_their_own_statistics():
    llm = OllamaLLM()
    llm._post = fake_ollama(SCRIPT)

    async def one(request):
        with call_log() as log:
            await llm.chat([{"role": "user", "content": request}], [])
            await llm.chat([{"role": "user", "content": request}, {"role": "tool", "content": "{}"}], [])
        return log

    slow, fast = await asyncio.gather(one("Plan CIS410"), one("Plan CIS450"))
    assert [c["output_tokens"] for c in slow] == [10, 11]
    assert [c["output_tokens"] for c in fast] == [20, 21]
    assert sorted(c["output_tokens"] for c in llm.stats) == [10, 11, 20, 21]


async def test_assistant_results_carry_only_their_own_model_calls():
    llm = OllamaLLM()  # one model client shared by two students' requests
    llm._post = fake_ollama(SCRIPT)
    async with Client(server) as client:
        tools = BannerTools(client)
        a, b = await asyncio.gather(SchedulingAssistant(tools, llm, "S10001", TERM).run("Plan CIS410"),
                                    SchedulingAssistant(tools, llm, "S10002", TERM).run("Plan CIS450"))
    assert [c["output_tokens"] for c in a.llm_calls] == [10, 11]
    assert [c["output_tokens"] for c in b.llm_calls] == [20, 21]


def test_model_statistics_on_the_client_object_are_bounded():
    llm = OllamaLLM(max_stats=3)
    llm._post = lambda payload: {"message": {"role": "assistant", "content": "ok"}, "eval_count": 1}
    for _ in range(5):
        asyncio.run(llm.chat([{"role": "user", "content": "Plan CIS410"}], []))
    assert len(llm.stats) == 3


async def test_evaluation_record_keeps_this_cases_model_calls_once():
    llm = OllamaLLM()
    llm._post = fake_ollama(SCRIPT)
    llm.stats.append({"output_tokens": 999})  # left over from another case
    record = await run_case({"id": "X1", "request": "Plan CIS410", "student_id": "S10001"}, TERM, llm, server)
    assert [c["output_tokens"] for c in record["llm_calls"]] == [10, 11]
    assert "llm_calls" not in record["result"] and llm.stats == []
