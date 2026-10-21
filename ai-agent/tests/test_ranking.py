"""Soft-preference ranking in the planner (no MCP, no LLM).

A small stub stands in for BannerTools so each test controls exactly which
sections exist. Hard rules still come from the real validate_schedule.
"""

import pytest

from agent.banner_tools import ToolCallError
from agent.planner import MAX_COMBINATIONS, PREFERENCE_NAMES, Preferences, plan_schedules
from scheduling.models import Course, Meeting, Section, Student

pytestmark = pytest.mark.anyio

TERM = "T1"


def sec(sid, course, days, start, end, capacity=30, enrolled=0):
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    meeting = Meeting(tuple(days), h1 * 60 + m1, h2 * 60 + m2)
    return Section(sid, course, TERM, "01", "in_person", capacity, enrolled, (meeting,))


class StubTools:
    def __init__(self, sections, student=None):
        self._sections = sections
        self._student = student or Student("S1", "IT", 18, True)
        self._courses = {c: Course(c, c, 3) for c in {s.course_id for s in sections}}

    async def student(self, _id):
        return self._student

    async def course(self, cid):
        if cid not in self._courses:
            raise ToolCallError(f"unknown course {cid}")
        return self._courses[cid]

    async def sections(self, cid, _term):
        return [s for s in self._sections if s.course_id == cid]


A_EARLY = sec("A1", "AAA", ["MON", "WED"], "08:00", "09:15")  # 120 min before 10:00
A_LATE = sec("A2", "AAA", ["MON", "WED"], "10:00", "11:15")
A_FRI = sec("A3", "AAA", ["FRI"], "10:00", "12:30")
B_EARLY = sec("B1", "BBB", ["TUE", "THU"], "09:00", "10:15")  # 60 min before 10:00
B_LATE = sec("B2", "BBB", ["TUE", "THU"], "13:00", "14:15")
ALL = [A_EARLY, A_LATE, A_FRI, B_EARLY, B_LATE]


async def plan(prefs, sections=ALL, **kw):
    return await plan_schedules(StubTools(sections), "S1", TERM, ["AAA", "BBB"], prefs, **kw)


async def test_soft_preferences_rank_and_never_invalidate():
    p = await plan(Preferences(earliest_start="10:00", required=()), max_options=10)
    ids = [o["section_ids"] for o in p.options]
    assert ids[0] == ["A2", "B2"] and p.options[0]["meets_all_preferences"]
    assert ["A1", "B1"] in ids  # worst case is still offered, not dropped
    assert ids[-1] == ["A1", "B1"]
    assert [o["rank"] for o in p.options] == list(range(1, len(ids) + 1))
    assert p.excluded == []


async def test_fewer_violations_beat_fewer_minutes():
    # A2+B1: one violation (60 min). A1+B2: one violation (120 min). A1+B1: two.
    p = await plan(Preferences(earliest_start="10:00", required=()), max_options=10)
    order = [tuple(o["section_ids"]) for o in p.options]
    assert order.index(("A2", "B1")) < order.index(("A1", "B2")) < order.index(("A1", "B1"))


async def test_required_preference_filters_but_soft_one_still_ranks():
    prefs = Preferences(earliest_start="10:00", avoid_days=("FRI",), required=("earliest_start",))
    p = await plan(prefs)
    flat = [s for o in p.options for s in o["section_ids"]]
    assert "A1" not in flat and "B1" not in flat  # required => removed
    assert p.options[-1]["section_ids"][0] == "A3"  # soft Friday wish => ranked last
    assert p.options[-1]["preference_violations"][0]["preference"] == "avoid_days"


async def test_default_preferences_are_all_required_as_before():
    assert Preferences().required == PREFERENCE_NAMES
    p = await plan(Preferences(earliest_start="10:00"))
    assert all(o["meets_all_preferences"] for o in p.options)


async def test_no_preferences_means_every_option_meets_them():
    p = await plan(Preferences())
    assert p.total_valid_options == 6 and all(o["meets_all_preferences"] for o in p.options)


async def test_hard_constraints_beat_preferences():
    # The only time-matching A section is full: a perfect-preference schedule is not offered.
    full = sec("A2", "AAA", ["MON", "WED"], "10:00", "11:15", capacity=1, enrolled=1)
    p = await plan(Preferences(earliest_start="10:00", required=()), sections=[A_EARLY, full, B_LATE])
    assert [o["section_ids"] for o in p.options] == [["A1", "B2"]]
    assert not p.options[0]["meets_all_preferences"]


async def test_truncation_is_reported_after_ranking():
    p = await plan(Preferences(earliest_start="10:00", required=()), max_options=2)
    assert len(p.options) == 2 and p.total_valid_options == 6 and p.options_truncated
    assert p.options[0]["section_ids"] == ["A2", "B2"]  # best kept, not first-found


async def test_search_cap_is_reported():
    many_a = [sec(f"A{i}", "AAA", ["MON"], "10:00", "10:30") for i in range(101)]
    many_b = [sec(f"B{i}", "BBB", ["TUE"], "10:00", "10:30") for i in range(101)]
    assert 101 * 101 > MAX_COMBINATIONS
    p = await plan(Preferences(), sections=many_a + many_b)
    assert p.search_capped and p.combinations_checked == MAX_COMBINATIONS


async def test_infeasible_request_reports_instead_of_inventing():
    clash = [sec("A1", "AAA", ["MON"], "10:00", "11:00"), sec("B1", "BBB", ["MON"], "10:30", "11:30")]
    p = await plan(Preferences(), sections=clash)
    assert p.options == [] and p.total_valid_options == 0
    assert p.rejection_counts == {"TIME_CONFLICT": 1}
