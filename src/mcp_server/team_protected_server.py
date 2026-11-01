"""Protected, read-only MCP interface for the team agent.

Uses the personal project's existing token verifier and
student-access policy, with team-compatible tool shapes.

No enrollment operations. Synthetic testing only.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from mcp import types
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from src.mcp_server import team_security as security
from src.mcp_server import team_backend_client as backend


mcp = MCPServer(
    "UNA Team Protected Academic MCP",
    token_verifier=security.TOKEN_VERIFIER,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(security.ISSUER_URL),
        resource_server_url=AnyHttpUrl(security.RESOURCE_URL),
        required_scopes=["academic.read"],
        validate_token_resource=security.VALIDATE_TOKEN_RESOURCE,
    ),
)


ERROR_MESSAGES = {
    "FORBIDDEN": "Academic access denied.",
    "NOT_FOUND": "Academic record not found.",
    "INVALID_ARGUMENT": "Invalid academic request.",
    "BACKEND_DATA": "Academic backend returned invalid data.",
    "UNAVAILABLE": "Academic backend is unavailable.",
}


def tool_error(code: str) -> types.CallToolResult:
    if code not in ERROR_MESSAGES:
        code = "UNAVAILABLE"

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=ERROR_MESSAGES[code],
            )
        ],
        structured_content={"error_code": code},
        is_error=True,
    )


async def guarded(
    operation: Callable[[], Awaitable[Any]],
    *,
    student_id: str | None = None,
):
    # Authorization MUST happen before backend access.
    try:
        if student_id is None:
            security.authorize_catalog_request()
        else:
            security.authorize_student_request(student_id)
    except Exception:
        return tool_error("FORBIDDEN")

    try:
        return await operation()
    except backend.TeamBackendError as error:
        return tool_error(error.code)
    except Exception:
        # Never expose internal errors or credentials.
        return tool_error("UNAVAILABLE")


@mcp.tool()
async def get_student_record(student_id: str) -> dict:
    """Read the authenticated student's academic profile."""
    return await guarded(
        lambda: backend.get_student_record(student_id),
        student_id=student_id,
    )


@mcp.tool()
async def get_course_history(student_id: str) -> list[dict]:
    """Read the authenticated student's course history."""
    return await guarded(
        lambda: backend.get_course_history(student_id),
        student_id=student_id,
    )


@mcp.tool()
async def get_course(course_id: str) -> dict:
    """Retrieve a course from the synthetic catalog."""
    return await guarded(
        lambda: backend.get_course(course_id),
    )


@mcp.tool()
async def search_courses(
    query: str = "",
    subject: str = "",
) -> list[dict]:
    """Search synthetic courses by text and subject."""
    return await guarded(
        lambda: backend.search_courses(query, subject),
    )


@mcp.tool()
async def get_course_sections(
    course_id: str,
    term_id: str,
) -> list[dict]:
    """List synthetic sections offered in a term."""
    return await guarded(
        lambda: backend.get_course_sections(course_id, term_id),
    )


@mcp.tool()
async def get_student_enrollments(
    student_id: str,
    term_id: str,
) -> list[dict]:
    """Read full already-enrolled synthetic section records."""
    return await guarded(
        lambda: backend.get_student_enrollments(
            student_id, term_id
        ),
        student_id=student_id,
    )
