"""The scheduling assistant: an LLM in a tool-calling loop with guardrails.

Division of labor (the project's core design rule):
- The LLM interprets the student's request, picks tool arguments, and
  explains results in plain language.
- Deterministic code decides everything academic: plan_schedule() runs the
  planner, which only returns combinations validate_schedule() accepted.

Guardrails enforced in code, not in the prompt:
1. Identity binding: student_id and term_id are fixed when the assistant is
   created (later: from the Entra login). No tool takes a student_id, and any
   argument the tool does not declare is rejected, so the model cannot ask
   for another student's records.
2. Argument validation: bad arguments return an error to the model instead
   of reaching the planner or MCP.
3. Grounding check: every section ID in the final answer must come from a
   plan_schedule option. If not, the model is asked to revise once; if it
   still fails, the answer is returned flagged grounded=False.
4. Step limit: the loop stops after max_steps model calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scheduling.models import VALID_DAYS

from .banner_tools import BannerTools, ToolCallError
from .llm import LLM
from .planner import Preferences, plan_schedules

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system.md"

# WORKING ASSUMPTION: section IDs look like the mock data's ("SEC1001").
SECTION_ID_PATTERN = re.compile(r"\bSEC\d+\b")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_COURSES = 8

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_my_record",
            "description": "Get the signed-in student's program, credit-hour limit and completed courses.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "Find courses by words in the course ID or title, optionally within a subject like CIS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to look for, e.g. 'network'."},
                    "subject": {"type": "string", "description": "Subject code, e.g. 'CIS'."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_schedule",
            "description": (
                "Build valid schedules for the signed-in student this term from a list of course IDs. "
                "Returns valid options, excluded courses with reasons, and why other combinations failed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Course IDs, e.g. ['CIS376', 'CIS410'].",
                    },
                    "earliest_start": {"type": "string", "description": "No class before this time, 24h 'HH:MM'."},
                    "latest_end": {"type": "string", "description": "No class after this time, 24h 'HH:MM'."},
                    "avoid_days": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(VALID_DAYS)},
                        "description": "Days to keep free, e.g. ['FRI'].",
                    },
                },
                "required": ["course_ids"],
            },
        },
    },
]

_ALLOWED_ARGS = {
    spec["function"]["name"]: set(spec["function"]["parameters"]["properties"])
    for spec in TOOL_SPECS
}


class ToolArgumentError(ValueError):
    pass


@dataclass
class TraceEntry:
    tool: str
    arguments: dict
    ok: bool
    result: Any


@dataclass
class AssistantResult:
    answer: str
    grounded: bool
    ungrounded_section_ids: list[str]
    stopped_reason: str  # "answered" | "max_steps"
    model_calls: int
    trace: list[TraceEntry] = field(default_factory=list)
    mcp_calls: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SchedulingAssistant:
    def __init__(
        self,
        tools: BannerTools,
        llm: LLM,
        student_id: str,
        term_id: str,
        max_steps: int = 8,
    ):
        self.tools = tools
        self.llm = llm
        self.student_id = student_id  # bound identity; never taken from the model
        self.term_id = term_id
        self.max_steps = max_steps
        self.system_prompt = PROMPT_PATH.read_text(encoding="utf-8").replace("{term_id}", term_id)

    # ------------------------------------------------------------ tools

    def _check_args(self, name: str, args: dict) -> None:
        if name not in _ALLOWED_ARGS:
            raise ToolArgumentError(f"Unknown tool '{name}'.")
        extra = set(args) - _ALLOWED_ARGS[name]
        if extra:
            raise ToolArgumentError(
                f"Unexpected argument(s): {', '.join(sorted(extra))}. "
                "This assistant can only use the signed-in student's records."
            )

    async def _get_my_record(self) -> dict:
        s = await self.tools.student(self.student_id)
        return {
            "program": s.program,
            "max_credit_hours": s.max_credit_hours,
            "active": s.active,
            "completed_courses": sorted(s.completed_courses),
        }

    async def _search_courses(self, query: str = "", subject: str = "") -> list[dict]:
        if not isinstance(query, str) or not isinstance(subject, str):
            raise ToolArgumentError("query and subject must be strings.")
        rows = await self.tools.search_courses(query=query, subject=subject)
        return [
            {k: c[k] for k in ("course_id", "title", "credit_hours", "prerequisites", "corequisites")}
            for c in rows
        ]

    async def _plan_schedule(
        self,
        course_ids: list[str],
        earliest_start: str | None = None,
        latest_end: str | None = None,
        avoid_days: list[str] | None = None,
    ) -> dict:
        if (
            not isinstance(course_ids, list)
            or not course_ids
            or not all(isinstance(c, str) and c.strip() for c in course_ids)
        ):
            raise ToolArgumentError("course_ids must be a non-empty list of course ID strings.")
        if len(course_ids) > MAX_COURSES:
            raise ToolArgumentError(f"At most {MAX_COURSES} courses per request.")
        for label, t in (("earliest_start", earliest_start), ("latest_end", latest_end)):
            if t not in (None, "") and not (isinstance(t, str) and _HHMM.match(t)):
                raise ToolArgumentError(f"{label} must be 24-hour 'HH:MM', got {t!r}.")
        days = [d.upper() for d in (avoid_days or [])]
        bad = [d for d in days if d not in VALID_DAYS]
        if bad:
            raise ToolArgumentError(f"avoid_days has invalid values {bad}; use {sorted(VALID_DAYS)}.")

        plan = await plan_schedules(
            self.tools,
            self.student_id,
            self.term_id,
            [c.strip().upper() for c in course_ids],
            Preferences(earliest_start or None, latest_end or None, tuple(days)),
        )
        result = plan.to_dict()
        result.pop("student_id", None)
        return result

    async def _run_tool(self, name: str, args: dict) -> tuple[bool, Any]:
        try:
            self._check_args(name, args)
            if name == "get_my_record":
                return True, await self._get_my_record()
            if name == "search_courses":
                return True, await self._search_courses(**args)
            return True, await self._plan_schedule(**args)
        except (ToolArgumentError, ToolCallError, TypeError) as e:
            return False, {"error": str(e)}

    # ------------------------------------------------------------ loop

    @staticmethod
    def _allowed_section_ids(trace: list[TraceEntry]) -> set[str]:
        ids: set[str] = set()
        for t in trace:
            if t.tool == "plan_schedule" and t.ok:
                for option in t.result.get("options", []):
                    ids.update(option["section_ids"])
        return ids

    async def run(self, request: str) -> AssistantResult:
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": request},
        ]
        trace: list[TraceEntry] = []
        revised = False

        for step in range(1, self.max_steps + 1):
            reply = await self.llm.chat(messages, TOOL_SPECS)

            if reply["tool_calls"]:
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply["content"],
                        "tool_calls": [
                            {"function": {"name": c["name"], "arguments": c["arguments"]}}
                            for c in reply["tool_calls"]
                        ],
                    }
                )
                for c in reply["tool_calls"]:
                    ok, result = await self._run_tool(c["name"], c["arguments"])
                    trace.append(TraceEntry(c["name"], c["arguments"], ok, result))
                    messages.append(
                        {"role": "tool", "tool_name": c["name"], "content": json.dumps(result)}
                    )
                continue

            answer = reply["content"]
            mentioned = set(SECTION_ID_PATTERN.findall(answer))
            ungrounded = sorted(mentioned - self._allowed_section_ids(trace))
            if ungrounded and not revised:
                revised = True
                messages.append({"role": "assistant", "content": answer})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your answer mentions section(s) {', '.join(ungrounded)} that were not in any "
                            "plan_schedule option. Rewrite it using only sections from the returned options, "
                            "calling plan_schedule if needed."
                        ),
                    }
                )
                continue

            return AssistantResult(
                answer=answer,
                grounded=not ungrounded,
                ungrounded_section_ids=ungrounded,
                stopped_reason="answered",
                model_calls=step,
                trace=trace,
                mcp_calls=list(self.tools.calls),
            )

        return AssistantResult(
            answer="Sorry, I couldn't finish planning this request. Please try rephrasing it.",
            grounded=True,
            ungrounded_section_ids=[],
            stopped_reason="max_steps",
            model_calls=self.max_steps,
            trace=trace,
            mcp_calls=list(self.tools.calls),
        )
