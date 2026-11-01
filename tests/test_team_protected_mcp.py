"""Synthetic trusted-context tests for protected team MCP tools.

These tests inject a fake already-verified identity.
They do NOT test JWT signatures or MCP HTTP authentication.
"""

import asyncio

import pytest

from mcp.server.auth.provider import AccessToken

from src.mcp_server import team_security as security
from src.mcp_server import team_backend_client as backend
from src.mcp_server import team_protected_server as server


def run(coroutine):
    return asyncio.run(coroutine)


def fake_token(
    *,
    student_object="student-a",
    scopes=None,
    issuer=None,
):
    return AccessToken(
        token="not-a-real-synthetic-test-token",
        client_id="synthetic-client",
        scopes=["academic.read"] if scopes is None else scopes,
        expires_at=9999999999,
        resource="synthetic-test-resource",
        subject="synthetic-test-subject",
        claims={
            "iss": security.ISSUER_URL if issuer is None else issuer,
            "tid": "synthetic-tenant",
            "oid": student_object,
        },
    )


@pytest.fixture
def sign_in(monkeypatch):
    def select(student="S10001", **token_options):
        object_id = "student-a" if student == "S10001" else "student-b"
        token = fake_token(
            student_object=object_id, **token_options
        )
        monkeypatch.setattr(
            security, "get_access_token", lambda: token
        )
        monkeypatch.setattr(
            security,
            "STUDENT_LOOKUP",
            {
                ("synthetic-tenant", "student-a"): "S10001",
                ("synthetic-tenant", "student-b"): "S10002",
            },
        )
        return token

    return select


def assert_error(result, code):
    assert result.is_error is True
    assert result.structured_content == {"error_code": code}


def test_student_can_read_own_record(sign_in):
    sign_in()
    result = run(server.get_student_record("S10001"))
    assert result["student_id"] == "S10001"


def test_student_can_read_own_history_and_enrollments(sign_in):
    sign_in()

    history = run(server.get_course_history("S10001"))
    enrolled = run(
        server.get_student_enrollments("S10001", "2027SP")
    )

    assert len(history) == 3
    assert all(x["student_id"] == "S10001" for x in history)
    assert [x["section_id"] for x in enrolled] == ["SEC1001"]


def test_second_student_gets_second_students_data(sign_in):
    sign_in("S10002")

    result = run(server.get_student_record("S10002"))
    enrolled = run(
        server.get_student_enrollments("S10002", "2027SP")
    )

    assert result["student_id"] == "S10002"
    assert [x["section_id"] for x in enrolled] == ["SEC2002"]


@pytest.mark.parametrize(
    "operation",
    [
        lambda: server.get_student_record("S10002"),
        lambda: server.get_course_history("S10002"),
        lambda: server.get_student_enrollments("S10002", "2027SP"),
    ],
)
def test_cross_student_access_denied(sign_in, operation):
    sign_in("S10001")
    assert_error(run(operation()), "FORBIDDEN")


def test_denied_before_backend_is_called(sign_in, monkeypatch):
    sign_in("S10001")

    async def forbidden_backend_access(*args, **kwargs):
        raise AssertionError("Unauthorized backend access")

    monkeypatch.setattr(
        backend, "get_student_record", forbidden_backend_access
    )

    assert_error(
        run(server.get_student_record("S10002")),
        "FORBIDDEN",
    )


def test_missing_scope_denied(sign_in):
    sign_in(scopes=[])
    assert_error(
        run(server.get_student_record("S10001")),
        "FORBIDDEN",
    )


def test_untrusted_issuer_denied(sign_in):
    sign_in(issuer="https://untrusted.invalid")
    assert_error(
        run(server.get_student_record("S10001")),
        "FORBIDDEN",
    )


def test_authenticated_catalog_access(sign_in):
    sign_in()

    course = run(server.get_course("CIS410"))
    sections = run(
        server.get_course_sections("CIS410", "2027SP")
    )
    matches = run(server.search_courses("secure", "CIS"))

    assert course["course_id"] == "CIS410"
    assert len(sections) == 2
    assert [x["course_id"] for x in matches] == ["CIS410"]


def test_missing_course_has_structured_error(sign_in):
    sign_in()
    assert_error(
        run(server.get_course("ZZZ999")),
        "NOT_FOUND",
    )


def test_backend_error_does_not_leak_detail(sign_in, monkeypatch):
    sign_in()

    async def broken_backend(*args, **kwargs):
        raise RuntimeError("PRIVATE_INTERNAL_DIAGNOSTIC")

    monkeypatch.setattr(
        backend, "get_course", broken_backend
    )

    result = run(server.get_course("CIS410"))
    assert_error(result, "UNAVAILABLE")
    assert "PRIVATE_INTERNAL_DIAGNOSTIC" not in str(result)
