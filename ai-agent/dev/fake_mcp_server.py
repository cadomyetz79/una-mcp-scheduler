"""Stand-in MCP server for developing the agent before the real one exists.

It serves the team's mock data (data/*.json) through MCP tools, so the agent
talks MCP from day one. When Workstream 2's real server is ready, the agent
connects to it instead and this file is only used in tests.

The tool names and return shapes here are a PROPOSAL (WORKING ASSUMPTION).
They live in one place on the agent side (agent/banner_tools.py: TOOL_NAMES),
so renaming them to match the real server is a one-line change per tool.

Run over stdio:
    python ai-agent/dev/fake_mcp_server.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DATA_DIR = Path(
    os.environ.get("UNA_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)

server = MCPServer("una-fake-banner")


def _load(name: str) -> list[dict]:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@server.tool()
def get_student_record(student_id: str) -> dict:
    """Return one student's scheduling profile (program, credit limit, active)."""
    for s in _load("students.json"):
        if s["student_id"] == student_id:
            return s
    raise ToolError(f"student {student_id} not found")


@server.tool()
def get_course_history(student_id: str) -> list[dict]:
    """Return every course attempt for a student (completed, failed, ...)."""
    if not any(s["student_id"] == student_id for s in _load("students.json")):
        raise ToolError(f"student {student_id} not found")
    return [h for h in _load("course_history.json") if h["student_id"] == student_id]


@server.tool()
def get_course(course_id: str) -> dict:
    """Return one course with credit hours, prerequisites and corequisites."""
    for c in _load("courses.json"):
        if c["course_id"] == course_id:
            return c
    raise ToolError(f"course {course_id} not found")


@server.tool()
def search_courses(query: str = "", subject: str = "") -> list[dict]:
    """Search courses by text in the ID or title, optionally filtered by subject."""
    q, subj = query.lower(), subject.upper()
    return [
        c
        for c in _load("courses.json")
        if (not subj or c["subject"] == subj)
        and (q in c["course_id"].lower() or q in c["title"].lower())
    ]


@server.tool()
def get_course_sections(course_id: str, term_id: str) -> list[dict]:
    """Return all sections of a course in a term, with meetings and seat counts."""
    return [
        s
        for s in _load("sections.json")
        if s["course_id"] == course_id and s["term_id"] == term_id
    ]


if __name__ == "__main__":
    server.run(transport="stdio")
