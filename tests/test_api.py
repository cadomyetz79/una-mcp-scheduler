"""Regression tests for the synthetic UNA Mock Banner API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def get_records(client, endpoint):
    response = client.get(endpoint)
    assert response.status_code == 200
    records = response.json()
    assert isinstance(records, list)
    return records


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "UNA Mock Banner API",
    }


@pytest.mark.parametrize(
    "endpoint",
    ["/students", "/courses", "/sections", "/course-history"],
)
def test_list_endpoints_return_records(client, endpoint):
    records = get_records(client, endpoint)
    assert records


@pytest.mark.parametrize(
    "endpoint,id_field",
    [
        ("/students", "student_id"),
        ("/courses", "course_id"),
        ("/sections", "section_id"),
    ],
)
def test_detail_endpoints_return_matching_record(client, endpoint, id_field):
    records = get_records(client, endpoint)
    expected = records[0]

    response = client.get(f"{endpoint}/{expected[id_field]}")

    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize(
    "endpoint,expected_message",
    [
        ("/students/UNKNOWN_TEST_ID", "Student not found"),
        ("/courses/UNKNOWN_TEST_ID", "Course not found"),
        ("/sections/UNKNOWN_TEST_ID", "Section not found"),
    ],
)
def test_missing_records_return_404(client, endpoint, expected_message):
    response = client.get(endpoint)

    assert response.status_code == 404
    assert response.json() == {"detail": expected_message}


@pytest.mark.parametrize(
    "filter_fields",
    [
        ("course_id",),
        ("term_id",),
        ("course_id", "term_id"),
    ],
)
def test_section_filters(client, filter_fields):
    sections = get_records(client, "/sections")
    selected = sections[0]

    params = {field: selected[field] for field in filter_fields}
    response = client.get("/sections", params=params)

    assert response.status_code == 200
    filtered = response.json()
    assert filtered

    expected = [
        section for section in sections
        if all(section[field] == value for field, value in params.items())
    ]
    assert filtered == expected


@pytest.mark.parametrize(
    "filter_fields",
    [
        ("student_id",),
        ("status",),
        ("student_id", "status"),
    ],
)
def test_course_history_filters(client, filter_fields):
    history = get_records(client, "/course-history")
    selected = history[0]

    params = {field: selected[field] for field in filter_fields}
    response = client.get("/course-history", params=params)

    assert response.status_code == 200
    filtered = response.json()
    assert filtered

    expected = [
        record for record in history
        if all(record[field] == value for field, value in params.items())
    ]
    assert filtered == expected


def test_student_course_history_matches_student(client):
    students = get_records(client, "/students")
    history = get_records(client, "/course-history")

    student_id = students[0]["student_id"]
    response = client.get(f"/students/{student_id}/course-history")

    assert response.status_code == 200
    expected = [
        record for record in history
        if record["student_id"] == student_id
    ]
    assert response.json() == expected


def test_unknown_student_course_history_returns_404(client):
    response = client.get(
        "/students/UNKNOWN_TEST_ID/course-history"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Student not found"}
