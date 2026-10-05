"""Typed access to the academic MCP tools.

Everything the agent knows about students, courses and sections comes
through this class, over MCP. It turns raw tool results into the models the
validators use, so the deterministic rules never see unparsed data.
"""

from __future__ import annotations

import json
from typing import Any

from mcp import Client

from scheduling.models import Course, Section, Student

# Agent-side name -> MCP tool name on the server.
# WORKING ASSUMPTION: proposed names. Update the right-hand side to match
# Workstream 2's real server; nothing else needs to change.
TOOL_NAMES = {
    "student": "get_student_record",
    "history": "get_course_history",
    "course": "get_course",
    "search": "search_courses",
    "sections": "get_course_sections",
}


class ToolCallError(RuntimeError):
    """An MCP tool returned is_error=True (e.g. unknown student)."""


class BannerTools:
    def __init__(self, client: Client):
        self._client = client
        self.calls: list[dict[str, Any]] = []  # audit log of every tool call

    async def _call(self, key: str, **arguments: Any) -> Any:
        name = TOOL_NAMES[key]
        result = await self._client.call_tool(name, arguments)
        self.calls.append({"tool": name, "arguments": arguments, "is_error": result.is_error})
        text = "".join(getattr(block, "text", "") for block in result.content)
        if result.is_error:
            raise ToolCallError(text or f"{name} failed")
        if result.structured_content is not None:
            data = result.structured_content
            # Servers wrap non-object results (e.g. lists) as {"result": ...}.
            return data["result"] if set(data) == {"result"} else data
        return json.loads(text) if text else None

    async def student(self, student_id: str) -> Student:
        record = await self._call("student", student_id=student_id)
        history = await self._call("history", student_id=student_id)
        return Student.from_dict(record, history)

    async def course(self, course_id: str) -> Course:
        return Course.from_dict(await self._call("course", course_id=course_id))

    async def search_courses(self, query: str = "", subject: str = "") -> list[dict]:
        return await self._call("search", query=query, subject=subject)

    async def sections(self, course_id: str, term_id: str) -> list[Section]:
        raw = await self._call("sections", course_id=course_id, term_id=term_id)
        return [Section.from_dict(s) for s in raw]
