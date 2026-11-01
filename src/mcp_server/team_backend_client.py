"""Read-only adapter to the team's synthetic Mock Banner API.

This is an internal data adapter, NOT an authenticated endpoint.
The protected MCP server must authorize each student request
before calling these functions.
"""

import re

import httpx

from app.main import app


class TeamBackendError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def check_id(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(
        pattern, value, flags=re.ASCII
    ):
        raise TeamBackendError("INVALID_ARGUMENT")
    return value


async def get_json(path, params=None):
    transport = httpx.ASGITransport(
        app=app, raise_app_exceptions=False
    )
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://mock-banner.invalid",
        ) as client:
            response = await client.get(path, params=params)
    except httpx.HTTPError:
        raise TeamBackendError("UNAVAILABLE") from None

    if response.status_code == 404:
        raise TeamBackendError("NOT_FOUND")
    if response.status_code != 200:
        raise TeamBackendError("UNAVAILABLE")

    try:
        return response.json()
    except ValueError:
        raise TeamBackendError("BACKEND_DATA") from None


def require_rows(value):
    if not isinstance(value, list) or not all(
        isinstance(row, dict) for row in value
    ):
        raise TeamBackendError("BACKEND_DATA")
    return value


def student_id(value):
    return check_id(value, r"S[0-9]+")


def course_id(value):
    return check_id(value, r"[A-Z]{2,4}[0-9]{3}")


def term_id(value):
    return check_id(value, r"[0-9]{4}[A-Z]{2}")


async def get_student_record(student):
    student = student_id(student)
    result = await get_json(f"/students/{student}")
    if not isinstance(result, dict) or result.get("student_id") != student:
        raise TeamBackendError("BACKEND_DATA")
    return result


async def get_course_history(student):
    student = student_id(student)
    rows = require_rows(
        await get_json(f"/students/{student}/course-history")
    )
    if any(row.get("student_id") != student for row in rows):
        raise TeamBackendError("BACKEND_DATA")
    return rows


async def get_course(course):
    course = course_id(course)
    result = await get_json(f"/courses/{course}")
    if not isinstance(result, dict) or result.get("course_id") != course:
        raise TeamBackendError("BACKEND_DATA")
    return result


async def search_courses(query="", subject=""):
    if not isinstance(query, str) or len(query) > 100:
        raise TeamBackendError("INVALID_ARGUMENT")
    if not isinstance(subject, str) or (
        subject and not re.fullmatch(r"[A-Z]{2,4}", subject)
    ):
        raise TeamBackendError("INVALID_ARGUMENT")

    rows = require_rows(await get_json("/courses"))
    results = []
    for row in rows:
        cid = row.get("course_id")
        title = row.get("title")
        code = row.get("subject")
        if not all(isinstance(x, str) for x in (cid, title, code)):
            raise TeamBackendError("BACKEND_DATA")
        if subject and code != subject:
            continue
        if query.casefold() in cid.casefold() or query.casefold() in title.casefold():
            results.append(row)
    return results


async def get_course_sections(course, term):
    course = course_id(course)
    term = term_id(term)
    rows = require_rows(
        await get_json(
            "/sections",
            params={"course_id": course, "term_id": term},
        )
    )
    if any(
        row.get("course_id") != course or row.get("term_id") != term
        for row in rows
    ):
        raise TeamBackendError("BACKEND_DATA")
    return rows


async def get_student_enrollments(student, term):
    student = student_id(student)
    term = term_id(term)
    enrollments = require_rows(
        await get_json(f"/students/{student}/enrollments")
    )
    results = []
    seen = set()

    for enrollment in enrollments:
        if enrollment.get("student_id") != student:
            raise TeamBackendError("BACKEND_DATA")
        if enrollment.get("status") != "enrolled":
            continue

        section_id = check_id(
            enrollment.get("section_id"), r"SEC[0-9]+"
        )
        if section_id in seen:
            raise TeamBackendError("BACKEND_DATA")
        seen.add(section_id)

        section = await get_json(f"/sections/{section_id}")
        if not isinstance(section, dict) or section.get("section_id") != section_id:
            raise TeamBackendError("BACKEND_DATA")
        if section.get("term_id") == term:
            results.append(section)

    return results
