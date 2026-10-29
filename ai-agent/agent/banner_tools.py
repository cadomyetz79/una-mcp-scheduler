"""Typed access to the academic MCP tools.

Everything the agent knows about students, courses and sections comes
through this class, over MCP. It turns raw tool results into the models the
validators use, so the deterministic rules never see unparsed data.

Errors (integration-readiness audit 2026-10-19, defects D1-D3). Every
failure becomes a BackendError subclass whose str() is a fixed, safe message:

- ToolCallError: the MCP tool returned is_error. `code` is "not_found",
  "unknown_tool" or "tool_error".
- BackendUnavailable: the call itself failed (connection closed, timeout,
  protocol error).
- BackendDataError: the server answered, but the data does not have the
  expected shape (missing field, "Mon" instead of "MON", "9:30 AM", non-JSON
  text).

The raw server or exception text is kept only in `.internal`. It is never
sent to the model, shown to a student or written to evaluation records;
`log_record()` gives a hash of it for correlating with server logs, because
server errors can contain hosts, user names or connection strings.

WORKING ASSUMPTION: "not found" is recognised from the error text ("not
found", "does not exist", "unknown student/course"), or from a structured
`error_code` field if the server sends one. A structured code should be part
of the contract with Workstream 2.

Per-request trace (D6): each call is appended to the log of the request in
progress (`run_log()`, a context variable, so concurrent requests on the
same MCP session never see each other's calls) and to `calls`, the
connection-wide audit list owned by whoever created this object.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from mcp import Client

from scheduling.models import Course, Section, Student, parse_course_ids

# Agent-side name -> MCP tool name on the server.
# WORKING ASSUMPTION: proposed names. Update the right-hand side to match
# Workstream 2's real server; nothing else needs to change.
TOOL_NAMES = {
    "student": "get_student_record",
    "history": "get_course_history",
    "course": "get_course",
    "search": "search_courses",
    "sections": "get_course_sections",
    # Optional (proposed 2026-10-19): sections the student is already
    # registered in for a term. If the server does not have it, the planner
    # reports that current registrations could not be checked.
    "enrollments": "get_student_enrollments",
}

_NOT_FOUND = re.compile(r"\bnot found\b|\bdoes not exist\b|\bno such\b|\bunknown (student|course|section|term)\b",
                        re.IGNORECASE)
_UNKNOWN_TOOL = re.compile(r"\bunknown tool\b|\btool '?[\w.-]+'? (is )?not (found|available)\b|method not found",
                           re.IGNORECASE)

_RUN_LOG: ContextVar[list | None] = ContextVar("una_mcp_run_log", default=None)


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


class BackendError(RuntimeError):
    """A failure of the academic backend. str(error) is always safe to show."""

    code = "backend_error"
    public_message = "The registration system could not complete this request."

    def __init__(self, internal: str = "", *, tool: str = ""):
        super().__init__(self.public_message)
        self.internal = internal  # raw detail: never shown, never logged in clear
        self.tool = tool

    def log_record(self) -> dict:
        return {"code": self.code, "tool": self.tool, "detail_sha256": _digest(self.internal),
                "detail_chars": len(self.internal or "")}


class ToolCallError(BackendError):
    """An MCP tool returned is_error=True (e.g. unknown student)."""

    _PUBLIC = {
        ("not_found", "get_student_record"): "Student record not found.",
        ("not_found", "get_course_history"): "Student record not found.",
        ("not_found", "get_course"): "Course not found in the catalog.",
        ("unknown_tool", ""): "This registration lookup is not available.",
    }

    def __init__(self, internal: str = "", *, tool: str = "", code: str | None = None):
        if code is None:
            code = ("unknown_tool" if _UNKNOWN_TOOL.search(internal or "")
                    else "not_found" if _NOT_FOUND.search(internal or "") else "tool_error")
        self.code = code
        self.public_message = (self._PUBLIC.get((code, tool)) or self._PUBLIC.get((code, ""))
                               or ("Not found in the registration system." if code == "not_found"
                                   else "The registration system returned an error for this request."))
        super().__init__(internal, tool=tool)


class BackendUnavailable(BackendError):
    code = "backend_unavailable"
    public_message = "The registration system is not reachable right now."


class BackendDataError(BackendError):
    code = "backend_data_error"
    public_message = "The registration system returned data in an unexpected format."


class BannerTools:
    def __init__(self, client: Client):
        self._client = client
        self.calls: list[dict[str, Any]] = []  # connection-wide audit log (owner's), see run_log()

    @staticmethod
    @contextmanager
    def run_log() -> Iterator[list[dict]]:
        """Collect the MCP calls of one request (safe under concurrent requests)."""
        log: list[dict] = []
        token = _RUN_LOG.set(log)
        try:
            yield log
        finally:
            _RUN_LOG.reset(token)

    def _record(self, entry: dict) -> None:
        self.calls.append(entry)
        log = _RUN_LOG.get()
        if log is not None:
            log.append(entry)

    async def _call(self, key: str, **arguments: Any) -> Any:
        name = TOOL_NAMES[key]
        try:
            result = await self._client.call_tool(name, arguments)
        except Exception as e:  # transport / protocol failure; cancellation still propagates
            self._record({"tool": name, "arguments": arguments, "is_error": True, "error_code": "backend_unavailable"})
            raise BackendUnavailable(f"{type(e).__name__}: {e}", tool=name) from None
        text = "".join(getattr(block, "text", "") or "" for block in (result.content or []))
        structured = result.structured_content
        if result.is_error:
            code = None
            if isinstance(structured, dict) and isinstance(structured.get("error_code"), str):
                code = {"NOT_FOUND": "not_found"}.get(structured["error_code"].upper(), "tool_error")
            error = ToolCallError(text or f"{name} failed", tool=name, code=code)
            self._record({"tool": name, "arguments": arguments, "is_error": True, "error_code": error.code})
            raise error
        self._record({"tool": name, "arguments": arguments, "is_error": False})
        if structured is not None:
            # Servers wrap non-object results (e.g. lists) as {"result": ...}.
            return structured["result"] if isinstance(structured, dict) and set(structured) == {"result"} \
                else structured
        try:
            return json.loads(text) if text else None
        except json.JSONDecodeError:
            raise BackendDataError("tool result is not JSON", tool=name) from None

    @staticmethod
    def _parse(tool: str, fn, raw: Any):
        """Run a model constructor on server data; a wrong shape is a BackendDataError."""
        try:
            return fn(raw)
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as e:
            raise BackendDataError(f"{type(e).__name__}: {e}", tool=tool) from None

    @staticmethod
    def _rows(tool: str, raw: Any) -> list:
        if not isinstance(raw, list):
            raise BackendDataError(f"expected a list, got {type(raw).__name__}", tool=tool)
        return raw

    async def student(self, student_id: str) -> Student:
        record = await self._call("student", student_id=student_id)
        history = self._rows(TOOL_NAMES["history"], await self._call("history", student_id=student_id))
        return self._parse(TOOL_NAMES["student"], lambda r: Student.from_dict(r, history), record)

    async def course(self, course_id: str) -> Course:
        return self._parse(TOOL_NAMES["course"], Course.from_dict, await self._call("course", course_id=course_id))

    async def search_courses(self, query: str = "", subject: str = "") -> list[dict]:
        rows = self._rows(TOOL_NAMES["search"], await self._call("search", query=query, subject=subject))

        def norm(c: dict) -> dict:
            if not isinstance(c, dict) or not isinstance(c.get("course_id"), str):
                raise ValueError("course row without course_id")
            return {"course_id": c["course_id"], "title": str(c.get("title") or ""),
                    "credit_hours": c.get("credit_hours"),
                    # same rule as Course.from_dict: an array of course IDs, or missing
                    "prerequisites": list(parse_course_ids(c.get("prerequisites", []), "prerequisites")),
                    "corequisites": list(parse_course_ids(c.get("corequisites", []), "corequisites"))}

        return [self._parse(TOOL_NAMES["search"], norm, c) for c in rows]

    async def sections(self, course_id: str, term_id: str) -> list[Section]:
        raw = self._rows(TOOL_NAMES["sections"], await self._call("sections", course_id=course_id, term_id=term_id))
        return [self._parse(TOOL_NAMES["sections"], Section.from_dict, s) for s in raw]

    async def enrollments(self, student_id: str, term_id: str) -> list[Section] | None:
        """Sections the student is already registered in this term, or None if
        the server cannot say (tool missing or failing); never a silent empty list."""
        try:
            raw = self._rows(TOOL_NAMES["enrollments"],
                             await self._call("enrollments", student_id=student_id, term_id=term_id))
            return [self._parse(TOOL_NAMES["enrollments"], Section.from_dict, s) for s in raw]
        except BackendError:
            return None
