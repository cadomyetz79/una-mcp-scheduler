"""Unit tests for edge cases the mock dataset does not cover yet."""

import pytest

from scheduling.models import Course, CourseRecord, Meeting, Section, Student
from scheduling.validators import (
    check_corequisites,
    check_credit_limit,
    check_time_conflicts,
    validate_schedule,
)


def meeting(days, start, end):
    return Meeting.from_dict({"days": days, "start_time": start, "end_time": end})


def section(sid, cid, meetings=(), term="2027SP", cap=30, enrolled=0):
    return Section(sid, cid, term, "01", "in_person", cap, enrolled, tuple(meetings))


def student(max_hours=18, done=(), active=True):
    hist = tuple(CourseRecord(c, "2026FA", "A", "completed") for c in done)
    return Student("S1", "IT", max_hours, active, hist)


# ---------------------------------------------------------------- time


def test_back_to_back_is_not_a_conflict():
    a = section("A", "C1", [meeting(["MON"], "09:00", "10:00")])
    b = section("B", "C2", [meeting(["MON"], "10:00", "11:00")])
    assert check_time_conflicts([a, b]) == []


def test_same_time_different_days_is_not_a_conflict():
    a = section("A", "C1", [meeting(["MON", "WED"], "09:00", "10:15")])
    b = section("B", "C2", [meeting(["TUE", "THU"], "09:00", "10:15")])
    assert check_time_conflicts([a, b]) == []


def test_lab_meeting_conflict_is_detected():
    # Lecture MW is fine, but the FRI lab overlaps the other course.
    a = section("A", "C1", [
        meeting(["MON", "WED"], "09:00", "10:15"),
        meeting(["FRI"], "13:00", "15:00"),
    ])
    b = section("B", "C2", [meeting(["FRI"], "14:00", "15:15")])
    assert [i.code for i in check_time_conflicts([a, b])] == ["TIME_CONFLICT"]


def test_online_section_without_meetings_never_conflicts():
    a = section("A", "C1", [meeting(["MON"], "09:00", "10:00")])
    b = section("B", "C2", [])
    assert check_time_conflicts([a, b]) == []


def test_invalid_meeting_data_is_rejected():
    with pytest.raises(ValueError):
        meeting(["MON"], "11:00", "10:00")
    with pytest.raises(ValueError):
        meeting(["MONDAY"], "09:00", "10:00")
    with pytest.raises(ValueError):
        meeting(["MON"], "25:00", "26:00")


# ---------------------------------------------------------------- credits


def test_credit_limit_boundary():
    courses = {f"C{i}": Course(f"C{i}", "", 3) for i in range(7)}
    six = [section(f"S{i}", f"C{i}") for i in range(6)]  # 18 hours
    seven = [section(f"S{i}", f"C{i}") for i in range(7)]  # 21 hours
    assert check_credit_limit(student(18), six, courses) == []
    assert [i.code for i in check_credit_limit(student(18), seven, courses)] == [
        "CREDIT_LIMIT_EXCEEDED"
    ]


# ---------------------------------------------------------------- corequisites


def test_corequisite_satisfied_in_same_schedule():
    courses = {
        "LEC": Course("LEC", "", 3, corequisites=("LAB",)),
        "LAB": Course("LAB", "", 1),
    }
    s = [section("S1", "LEC"), section("S2", "LAB")]
    assert check_corequisites(student(), s, courses) == []


def test_corequisite_missing():
    courses = {"LEC": Course("LEC", "", 3, corequisites=("LAB",))}
    issues = check_corequisites(student(), [section("S1", "LEC")], courses)
    assert [i.code for i in issues] == ["MISSING_COREQUISITE"]


def test_corequisite_satisfied_by_completed_course():
    courses = {"LEC": Course("LEC", "", 3, corequisites=("LAB",))}
    assert check_corequisites(student(done=["LAB"]), [section("S1", "LEC")], courses) == []


# ---------------------------------------------------------------- full flow


def test_retaking_completed_course_is_flagged():
    courses = {"C1": Course("C1", "", 3)}
    r = validate_schedule(student(done=["C1"]), ["S1"], "2027SP",
                          {"S1": section("S1", "C1")}, courses)
    assert [i.code for i in r.issues] == ["ALREADY_COMPLETED"]


def test_empty_schedule_is_valid():
    r = validate_schedule(student(), [], "2027SP", {}, {})
    assert r.valid and r.total_credit_hours == 0
