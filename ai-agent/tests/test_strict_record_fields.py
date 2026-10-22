"""Strict reading of two record fields (contract gaps G1 and G2, 2026-10-22).

G1  `active` must be a JSON boolean. bool("false") is True, so a student
    record sent with "active": "false" used to be read as an ACTIVE student
    and could get schedules. Any non-boolean value is now a data error: the
    request fails closed with the fixed data-error message.
G2  `prerequisites` and `corequisites` must be arrays of course IDs. A string
    used to be split into characters ("CIS376" -> "C", "I", "S", ...). It is
    now a data error, in Course.from_dict and in search_courses rows.

A missing `prerequisites` / `corequisites` field still means "none"; a
missing `active` field is still a data error (it is required).
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from mcp import Client

import dev.fake_mcp_server as fake
from agent.assistant import SchedulingAssistant
from agent.banner_tools import BackendDataError, BannerTools
from agent.llm import ScriptedLLM, call
from agent.planner import plan_schedules
from dev.fake_mcp_server import server
from scheduling.loader import load_dataset
from scheduling.models import Course, Section, Student, parse_bool, parse_course_ids
from scheduling.validators import validate_schedule

pytestmark = pytest.mark.anyio

TERM = "2027SP"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "data"
STUDENT = {"student_id": "S1", "program": "IT", "max_credit_hours": 18}
COURSE = {"course_id": "CIS410", "title": "Network Security", "credit_hours": 3}
INVALID_ACTIVE = ["false", "true", "False", "", "0", 0, 1, 0.0, None, [], {}]
INVALID_COURSE_IDS = ["CIS376", "", "CIS376,CIS236", None, 3, {"CIS376": True}, ["CIS376", 5], ["CIS376", ""],
                      [None], ["  "], [["CIS376"]]]


# ------------------------------------------------------------------ G1: models


@pytest.mark.parametrize("value", [True, False])
def test_active_accepts_json_booleans(value):
    assert Student.from_dict({**STUDENT, "active": value}).active is value


@pytest.mark.parametrize("value", INVALID_ACTIVE, ids=repr)
def test_active_rejects_every_non_boolean(value):
    with pytest.raises(ValueError, match="active must be a JSON boolean"):
        Student.from_dict({**STUDENT, "active": value})


def test_active_is_still_required():
    with pytest.raises(KeyError):
        Student.from_dict(dict(STUDENT))


def test_an_inactive_student_is_still_reported_inactive():
    student = Student.from_dict({**STUDENT, "active": False})
    section = Section.from_dict({"section_id": "SEC9", "course_id": "CIS410", "term_id": TERM,
                                 "capacity": 30, "enrolled_count": 0})
    result = validate_schedule(student, ["SEC9"], TERM, {"SEC9": section}, {"CIS410": Course.from_dict(COURSE)})
    assert [i.code for i in result.issues] == ["STUDENT_INACTIVE"]


def test_the_error_names_the_type_not_the_value():
    with pytest.raises(ValueError) as e:
        parse_bool("not-a-real-value", "active")
    assert "not-a-real-value" not in str(e.value) and "str" in str(e.value)


# ------------------------------------------------------------------ G2: models


@pytest.mark.parametrize("field", ["prerequisites", "corequisites"])
@pytest.mark.parametrize("value,expected", [
    (["CIS376"], ("CIS376",)),
    (["CIS376", "CIS236"], ("CIS376", "CIS236")),
    ([], ()),
    (("CIS376",), ("CIS376",)),  # a tuple from Python code is an array too
])
def test_course_id_arrays_are_read_as_given(field, value, expected):
    assert getattr(Course.from_dict({**COURSE, field: value}), field) == expected


def test_missing_prerequisites_and_corequisites_mean_none():
    course = Course.from_dict(COURSE)
    assert course.prerequisites == () and course.corequisites == ()


@pytest.mark.parametrize("field", ["prerequisites", "corequisites"])
@pytest.mark.parametrize("value", INVALID_COURSE_IDS, ids=repr)
def test_malformed_course_id_lists_are_rejected_not_split(field, value):
    with pytest.raises(ValueError, match=field):
        Course.from_dict({**COURSE, field: value})


def test_a_string_is_never_split_into_characters():
    with pytest.raises(ValueError, match="must be an array"):
        parse_course_ids("CIS376", "prerequisites")


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
            for k, v in fields.items():
                if v is ...:
                    del row[k]
    (d / name).write_text(json.dumps(rows), encoding="utf-8")


async def test_string_active_from_the_server_is_a_data_error(data_copy):
    edit(data_copy, "students.json", "student_id", "S10001", active="false")
    async with Client(server) as client:
        tools = BannerTools(client)
        with pytest.raises(BackendDataError) as e:
            await tools.student("S10001")
        with pytest.raises(BackendDataError):
            await plan_schedules(tools, "S10001", TERM, ["CIS376"])
    assert str(e.value) == BackendDataError.public_message
    assert e.value.tool == "get_student_record"


async def test_no_schedule_is_offered_when_the_active_flag_cannot_be_read(data_copy):
    edit(data_copy, "students.json", "student_id", "S10001", active="false")
    answer = {"role": "assistant", "content": "I couldn't read your student record, so I can't plan this now.",
              "tool_calls": []}
    plan = {"role": "assistant", "content": "", "tool_calls": [call("plan_schedule", course_ids=["CIS376"])]}
    # the model's plan call fails; its answer is nudged once, then the system's own plan call fails too
    llm = ScriptedLLM([plan, answer, answer, answer])
    async with Client(server) as client:
        result = await SchedulingAssistant(BannerTools(client), llm, "S10001", TERM).run("Plan CIS376 for me.")
    plans = [t for t in result.trace if t.tool == "plan_schedule"]
    assert plans and all(not t.ok and t.result["error_code"] == "backend_data_error" for t in plans)
    assert not re.search(r"\bSEC\d+", result.answer)  # no section offered
    assert result.evidence_missing == ["CIS376"]
    assert {(b["code"], b["tool"]) for b in result.security["backend_errors"]} == {
        ("backend_data_error", "get_student_record")}


async def test_a_real_false_still_gives_an_inactive_student(data_copy):
    edit(data_copy, "students.json", "student_id", "S10001", active=False)
    async with Client(server) as client:
        assert (await BannerTools(client).student("S10001")).active is False


async def test_string_prerequisites_from_the_server_are_a_data_error(data_copy):
    edit(data_copy, "courses.json", "course_id", "CIS410", prerequisites="CIS376")
    async with Client(server) as client:
        tools = BannerTools(client)
        with pytest.raises(BackendDataError) as e:
            await tools.course("CIS410")
        # never reported as an unknown course and never planned with garbled prerequisites
        with pytest.raises(BackendDataError):
            await plan_schedules(tools, "S10001", TERM, ["CIS410"])
        with pytest.raises(BackendDataError) as search:
            await tools.search_courses("", "")
    assert e.value.tool == "get_course" and search.value.tool == "search_courses"


async def test_string_corequisites_in_a_search_row_are_a_data_error(data_copy):
    edit(data_copy, "courses.json", "course_id", "CIS410", corequisites="CIS376")
    async with Client(server) as client:
        with pytest.raises(BackendDataError):
            await BannerTools(client).search_courses("CIS410", "")


async def test_missing_prerequisites_from_the_server_mean_none(data_copy):
    edit(data_copy, "courses.json", "course_id", "CIS410", prerequisites=..., corequisites=...)
    async with Client(server) as client:
        tools = BannerTools(client)
        course = await tools.course("CIS410")
        [row] = await tools.search_courses("CIS410", "")
    assert course.prerequisites == () and course.corequisites == ()
    assert row["prerequisites"] == [] and row["corequisites"] == []


async def test_valid_search_rows_are_unchanged():
    async with Client(server) as client:
        rows = await BannerTools(client).search_courses("", "")
    raw = {c["course_id"]: c for c in json.loads((DATA / "courses.json").read_text(encoding="utf-8"))}
    assert rows and all(r["prerequisites"] == raw[r["course_id"]]["prerequisites"]
                        and r["corequisites"] == raw[r["course_id"]]["corequisites"] for r in rows)


# ------------------------------------------------------------------ bundled data still loads


@pytest.mark.parametrize("data_dir", [
    DATA,
    ROOT / "evaluation" / "heldout" / "data",
    ROOT / "evaluation" / "heldout2" / "data",
    ROOT / "evaluation" / "security" / "data",
], ids=lambda p: p.relative_to(ROOT.parent).as_posix())
def test_every_bundled_dataset_follows_the_strict_rules(data_dir):
    ds = load_dataset(data_dir)
    assert ds.students and ds.courses
    assert all(isinstance(s.active, bool) for s in ds.students.values())
