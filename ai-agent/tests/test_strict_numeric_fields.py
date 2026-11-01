"""Strict reading of numeric, day and time fields (data-validation audit F1-F5,
2026-10-29).

F1  credit_hours, capacity, enrolled_count and max_credit_hours were read
    with int(): 3.9 became 3, True became 1, "3" and " 4 " were accepted. Five
    3.9-credit courses (19.5 hours) passed an 18-hour limit as 15, and an
    enrolled count of 29.9 in a 30-seat section left one seat "open". They
    must now be whole JSON numbers (3.0 is still read as 3).
F2  Negative values were accepted: a -3 credit course lowered the total, and
    capacity -5 / enrolled -10 showed 5 open seats. They are now rejected.
F3  A meeting with "days": [] was accepted and never conflicted with
    anything; a dict of days was read as its keys. Days must be a non-empty
    array of day codes. (A section with no meetings, e.g. online, is unchanged.)
F4  parse_time accepted "9:5" (09:05 or a cut-off 09:50?), "+9:00", " 9:00"
    and non-ASCII digits. Only 24-hour "HH:MM" is accepted.
F5  An Infinity in a JSON text result made int() raise OverflowError, which
    BannerTools._parse did not catch, so it surfaced as a system error instead
    of the fixed data-error message.

Every rejection is a ValueError, so BannerTools reports a BackendDataError
and the request fails closed.
"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import Client

import dev.fake_mcp_server as fake
from agent.banner_tools import BackendDataError, BannerTools
from agent.planner import plan_schedules
from dev.fake_mcp_server import server
from scheduling.models import Course, Meeting, Section, Student, parse_count, parse_time
from scheduling.validators import validate_schedule

pytestmark = pytest.mark.anyio

TERM = "2027SP"
DATA = Path(__file__).resolve().parents[2] / "data"
STUDENT = {"student_id": "S1", "program": "IT", "max_credit_hours": 18, "active": True}
COURSE = {"course_id": "CIS410", "title": "Network Security", "credit_hours": 3}
SECTION = {"section_id": "SEC9", "course_id": "CIS410", "term_id": TERM, "capacity": 30, "enrolled_count": 0}
MEETING = {"days": ["MON", "WED"], "start_time": "09:30", "end_time": "10:45"}

# (constructor, base record, field)
NUMERIC_FIELDS = [
    (Course.from_dict, COURSE, "credit_hours"),
    (Section.from_dict, SECTION, "capacity"),
    (Section.from_dict, SECTION, "enrolled_count"),
    (Student.from_dict, STUDENT, "max_credit_hours"),
]
FIELD_IDS = [f for _, _, f in NUMERIC_FIELDS]
NOT_WHOLE_NUMBERS = [3.9, 0.5, True, False, "3", " 4 ", "1_0", "٣", "", None, [], {}, [3],
                     float("nan"), float("inf"), float("-inf")]


# ------------------------------------------------------------------ F1 / F2: models


@pytest.mark.parametrize("make,base,field", NUMERIC_FIELDS, ids=FIELD_IDS)
@pytest.mark.parametrize("value,expected", [(0, 0), (3, 3), (18, 18), (3.0, 3)])
def test_whole_numbers_are_read_as_given(make, base, field, value, expected):
    got = getattr(make({**base, field: value}), field)
    assert got == expected and type(got) is int


@pytest.mark.parametrize("make,base,field", NUMERIC_FIELDS, ids=FIELD_IDS)
@pytest.mark.parametrize("value", NOT_WHOLE_NUMBERS, ids=repr)
def test_values_that_are_not_whole_numbers_are_rejected(make, base, field, value):
    with pytest.raises(ValueError, match=field):
        make({**base, field: value})


@pytest.mark.parametrize("make,base,field", NUMERIC_FIELDS, ids=FIELD_IDS)
@pytest.mark.parametrize("value", [-1, -3, -1.0])
def test_negative_values_are_rejected(make, base, field, value):
    with pytest.raises(ValueError, match=f"{field} must not be negative"):
        make({**base, field: value})


@pytest.mark.parametrize("make,base,field", NUMERIC_FIELDS, ids=FIELD_IDS)
def test_numeric_fields_are_still_required(make, base, field):
    with pytest.raises(KeyError):
        make({k: v for k, v in base.items() if k != field})


def test_the_error_names_the_type_not_the_value():
    with pytest.raises(ValueError) as e:
        parse_count("not-a-real-value", "capacity")
    assert "not-a-real-value" not in str(e.value) and "str" in str(e.value)


def test_a_fractional_credit_can_no_longer_slip_under_the_credit_limit():
    # 5 x 3.9 = 19.5 hours; int() read it as 15 and passed an 18-hour limit.
    with pytest.raises(ValueError, match="credit_hours"):
        Course.from_dict({**COURSE, "credit_hours": 3.9})


def test_a_negative_credit_can_no_longer_lower_the_total():
    with pytest.raises(ValueError, match="credit_hours"):
        Course.from_dict({**COURSE, "credit_hours": -3})


def test_over_enrolment_is_still_read_and_still_full():
    s = Section.from_dict({**SECTION, "capacity": 30, "enrolled_count": 32})
    student = Student.from_dict(STUDENT)
    result = validate_schedule(student, ["SEC9"], TERM, {"SEC9": s}, {"CIS410": Course.from_dict(COURSE)})
    assert s.seats_available == -2 and [i.code for i in result.issues] == ["SECTION_FULL"]


# ------------------------------------------------------------------ F3: meeting days


@pytest.mark.parametrize("days", [[], (), None, "MON", "MONWED", {"MON": 1}, {"MON"}, [1], ["MON", 1],
                                  ["Mon"], ["MONDAY"], [["MON"]], 7], ids=repr)
def test_malformed_meeting_days_are_rejected(days):
    with pytest.raises(ValueError, match="day"):
        Meeting.from_dict({**MEETING, "days": days})


@pytest.mark.parametrize("days,expected", [
    (["MON"], ("MON",)),
    (["MON", "WED"], ("MON", "WED")),
    (("TUE", "THU"), ("TUE", "THU")),
    (["SAT", "SUN"], ("SAT", "SUN")),
])
def test_valid_meeting_days_are_read_as_given(days, expected):
    assert Meeting.from_dict({**MEETING, "days": days}).days == expected


def test_meeting_days_are_still_required():
    with pytest.raises(KeyError):
        Meeting.from_dict({k: v for k, v in MEETING.items() if k != "days"})


def test_a_section_without_meetings_is_still_valid():
    assert Section.from_dict({**SECTION, "meetings": []}).meetings == ()
    assert Section.from_dict(SECTION).meetings == ()


# ------------------------------------------------------------------ F4: times


@pytest.mark.parametrize("value,expected", [
    ("00:00", 0), ("09:30", 570), ("10:45", 645), ("23:59", 1439),
])
def test_strict_times_are_read_as_given(value, expected):
    assert parse_time(value) == expected


@pytest.mark.parametrize("value", [
    "9:30", "9:5", "09:5", "+9:00", " 09:00", "09:00 ", "09:00\n", "24:00", "23:60", "09:00:00",
    "0930", "09-30", "9:30 AM", "", ":", "٠٩:٣٠", "0٩:30", "1_0:00", None, 930, 9.5,
], ids=repr)
def test_malformed_times_are_rejected(value):
    with pytest.raises(ValueError, match="invalid time"):
        parse_time(value)


@pytest.mark.parametrize("field", ["start_time", "end_time"])
def test_a_malformed_meeting_time_is_rejected(field):
    with pytest.raises(ValueError, match="invalid time"):
        Meeting.from_dict({**MEETING, field: "9:5"})


# ------------------------------------------------------------------ through MCP (fake server)


@pytest.fixture
def data_copy(tmp_path, monkeypatch):
    """A copy of data/ that a test may edit; the fake MCP server reads it."""
    d = tmp_path / "data"
    shutil.copytree(DATA, d)
    monkeypatch.setattr(fake, "DATA_DIR", d)
    return d


def edit(d: Path, name: str, key: str, row_id: str, **fields):
    rows = json.loads((d / name).read_text(encoding="utf-8"))
    for row in rows:
        if row[key] == row_id:
            row.update(fields)
    (d / name).write_text(json.dumps(rows), encoding="utf-8")


async def test_fractional_credit_hours_from_the_server_are_a_data_error(data_copy):
    edit(data_copy, "courses.json", "course_id", "CIS410", credit_hours=3.9)
    async with Client(server) as client:
        tools = BannerTools(client)
        with pytest.raises(BackendDataError) as e:
            await tools.course("CIS410")
        with pytest.raises(BackendDataError):
            await plan_schedules(tools, "S10001", TERM, ["CIS410"])
    assert str(e.value) == BackendDataError.public_message and e.value.tool == "get_course"


async def test_a_fractional_enrolled_count_never_opens_a_full_section(data_copy):
    # SEC1002 is full (30/30); 29.9 used to be read as 29, i.e. one open seat.
    edit(data_copy, "sections.json", "section_id", "SEC1002", enrolled_count=29.9)
    async with Client(server) as client:
        tools = BannerTools(client)
        with pytest.raises(BackendDataError) as e:
            await tools.sections("CIS376", TERM)
        with pytest.raises(BackendDataError):
            await plan_schedules(tools, "S10001", TERM, ["CIS376"])
    assert e.value.tool == "get_course_sections"


async def test_negative_capacity_from_the_server_is_a_data_error(data_copy):
    edit(data_copy, "sections.json", "section_id", "SEC2001", capacity=-5, enrolled_count=-10)
    async with Client(server) as client:
        with pytest.raises(BackendDataError):
            await BannerTools(client).sections("CIS410", TERM)


async def test_a_boolean_credit_limit_from_the_server_is_a_data_error(data_copy):
    edit(data_copy, "students.json", "student_id", "S10001", max_credit_hours=True)
    async with Client(server) as client:
        with pytest.raises(BackendDataError) as e:
            await BannerTools(client).student("S10001")
    assert e.value.tool == "get_student_record"


async def test_a_meeting_without_days_from_the_server_is_a_data_error(data_copy):
    rows = json.loads((data_copy / "sections.json").read_text(encoding="utf-8"))
    meetings = next(r for r in rows if r["section_id"] == "SEC1001")["meetings"]
    edit(data_copy, "sections.json", "section_id", "SEC1001", meetings=[{**meetings[0], "days": []}])
    async with Client(server) as client:
        tools = BannerTools(client)
        with pytest.raises(BackendDataError):
            await tools.sections("CIS376", TERM)
        with pytest.raises(BackendDataError):
            await plan_schedules(tools, "S10001", TERM, ["CIS376", "CIS410"])


async def test_a_malformed_meeting_time_from_the_server_is_a_data_error(data_copy):
    rows = json.loads((data_copy / "sections.json").read_text(encoding="utf-8"))
    meetings = next(r for r in rows if r["section_id"] == "SEC1001")["meetings"]
    edit(data_copy, "sections.json", "section_id", "SEC1001", meetings=[{**meetings[0], "start_time": "9:5"}])
    async with Client(server) as client:
        with pytest.raises(BackendDataError):
            await BannerTools(client).sections("CIS376", TERM)


async def test_the_bundled_data_still_plans_as_before():
    async with Client(server) as client:
        result = await plan_schedules(BannerTools(client), "S10001", TERM, ["CIS376", "CIS410"])
    assert result.options and not result.excluded
    assert all(o["total_credit_hours"] == 6 for o in result.options)


# ------------------------------------------------------------------ F5: Infinity in a text result


class _TextClient:
    """An MCP client whose tool returns JSON text only (no structured content)."""

    def __init__(self, text: str):
        self.text = text

    async def call_tool(self, name, arguments):
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)], structured_content=None, is_error=False)


@pytest.mark.parametrize("number", ["Infinity", "-Infinity", "NaN", "1e400"])
async def test_a_non_finite_number_in_a_text_result_is_a_data_error(number):
    tools = BannerTools(_TextClient(f'{{"course_id": "CIS410", "title": "x", "credit_hours": {number}}}'))
    with pytest.raises(BackendDataError) as e:
        await tools.course("CIS410")
    assert str(e.value) == BackendDataError.public_message and e.value.tool == "get_course"


def test_an_overflow_in_a_model_constructor_is_a_data_error():
    # Defence in depth: any OverflowError while reading server data is a data error.
    with pytest.raises(BackendDataError) as e:
        BannerTools._parse("get_course", lambda raw: int(raw), float("inf"))
    assert e.value.code == "backend_data_error" and "OverflowError" in e.value.internal
