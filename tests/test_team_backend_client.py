"""Offline contract tests for the internal team Banner adapter."""

import asyncio

import pytest

from src.mcp_server import team_backend_client as backend


def run(coroutine):
    return asyncio.run(coroutine)


def test_student_and_history():
    student = run(backend.get_student_record("S10001"))
    history = run(backend.get_course_history("S10001"))

    assert student["student_id"] == "S10001"
    assert len(history) == 3
    assert all(row["student_id"] == "S10001" for row in history)


def test_course_search_and_sections():
    course = run(backend.get_course("CIS410"))
    matches = run(backend.search_courses("secure", "CIS"))
    sections = run(backend.get_course_sections("CIS410", "2027SP"))

    assert course["course_id"] == "CIS410"
    assert [row["course_id"] for row in matches] == ["CIS410"]
    assert {row["section_id"] for row in sections} == {
        "SEC2001", "SEC2002"
    }


def test_no_sections_for_other_term():
    assert run(
        backend.get_course_sections("CIS410", "2026FA")
    ) == []


def test_student_enrollments_are_filtered():
    first = run(backend.get_student_enrollments("S10001", "2027SP"))
    second = run(backend.get_student_enrollments("S10002", "2027SP"))

    assert [row["section_id"] for row in first] == ["SEC1001"]
    assert [row["section_id"] for row in second] == ["SEC2002"]


@pytest.mark.parametrize(
    "operation",
    [
        lambda: backend.get_student_record("S10001/../../"),
        lambda: backend.get_course("CIS410/other"),
        lambda: backend.get_course_sections("CIS410", "2027SPR"),
        lambda: backend.search_courses("test", "bad subject"),
    ],
)
def test_invalid_input_rejected(operation):
    with pytest.raises(backend.TeamBackendError) as error:
        run(operation())

    assert error.value.code == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "operation",
    [
        lambda: backend.get_student_record("S99999"),
        lambda: backend.get_course_history("S99999"),
        lambda: backend.get_course("ZZZ999"),
    ],
)
def test_missing_records_rejected(operation):
    with pytest.raises(backend.TeamBackendError) as error:
        run(operation())

    assert error.value.code == "NOT_FOUND"


def test_mismatched_student_history_rejected(monkeypatch):
    async def bad_response(path, params=None):
        return [{
            "student_id": "S10002",
            "course_id": "CIS330",
            "term_id": "2026FA",
            "status": "completed",
        }]

    monkeypatch.setattr(backend, "get_json", bad_response)

    with pytest.raises(backend.TeamBackendError) as error:
        run(backend.get_course_history("S10001"))

    assert error.value.code == "BACKEND_DATA"
