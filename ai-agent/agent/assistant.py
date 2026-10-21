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
5. Evidence check (agent/evidence.py), when the model tries to answer:
   - If the request needs plan_schedule evidence (taking / planning /
     availability for course IDs that are known) and no plan covers them,
     the model is told once which call is missing. If it still answers
     without it, and the course IDs are known and the request states no
     time/day wishes (so nothing would be left out), the assistant runs
     plan_schedule itself once and asks the model to answer from it.
     Otherwise the answer is marked with the missing evidence.
   - Availability/eligibility claims ("is offered", "you can take") need a
     matching plan_schedule result; catalog search alone is not enough.
   - A section the student named may be mentioned while rejecting it; any
     other section outside the plan options is ungrounded.
   Unsupported claims and ungrounded sections get one forced revision, then
   the answer is returned flagged grounded=False.
6. Preference strength check (agent/preference_language.py): when the
   student's own words clearly mark a stated preference as optional ("if
   possible") or mandatory ("can't"), that wins over the model's
   required_preferences. Ambiguous wording leaves the model's choice alone.
   Every correction is reported in the tool result and the trace.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scheduling.models import VALID_DAYS

from .banner_tools import BannerTools, ToolCallError
from .evidence import (
    has_preference_wording,
    missing_plan_evidence,
    required_courses,
    section_mentions,
    unsupported_claims,
)
from .llm import LLM
from .planner import PREFERENCE_NAMES, Preferences, plan_schedules
from .preference_language import reconcile

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system.md"

# WORKING ASSUMPTION: section IDs look like the mock data's ("SEC1001").
SECTION_ID_PATTERN = re.compile(r"\bSEC\d+\b")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# Argument names that would select a person; rejected with the privacy message.
_IDENTITY_ARG = re.compile(r"student|user|person|^id$|email|name", re.IGNORECASE)
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
                    "required_preferences": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(PREFERENCE_NAMES)},
                        "description": (
                            "Which of earliest_start, latest_end, avoid_days are MANDATORY because the "
                            "student said they must/can't. Leave out for ordinary wishes: those only rank the options."
                        ),
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
    by: str = "model"  # "model" or "system" (evidence-check recovery)


@dataclass
class AssistantResult:
    answer: str
    grounded: bool
    ungrounded_section_ids: list[str]
    stopped_reason: str  # "answered" | "max_steps"
    model_calls: int
    trace: list[TraceEntry] = field(default_factory=list)
    mcp_calls: list[dict] = field(default_factory=list)
    unsupported_claims: list[dict] = field(default_factory=list)
    rejected_section_mentions: list[str] = field(default_factory=list)
    evidence_missing: list[str] = field(default_factory=list)
    recoveries: list[dict] = field(default_factory=list)  # nudges and system-run tools

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
        check_preference_language: bool = True,
        check_evidence: bool = True,
    ):
        self.tools = tools
        self.llm = llm
        self.student_id = student_id  # bound identity; never taken from the model
        self.term_id = term_id
        self.max_steps = max_steps
        self.check_preference_language = check_preference_language
        self.check_evidence = check_evidence
        self._request = ""
        self.system_prompt = PROMPT_PATH.read_text(encoding="utf-8").replace("{term_id}", term_id)

    # ------------------------------------------------------------ tools

    def _check_args(self, name: str, args: dict) -> None:
        if name not in _ALLOWED_ARGS:
            raise ToolArgumentError(f"Unknown tool '{name}'.")
        extra = set(args) - _ALLOWED_ARGS[name]
        if not extra:
            return
        allowed = ", ".join(sorted(_ALLOWED_ARGS[name])) or "none"
        message = f"{name} does not accept: {', '.join(sorted(extra))}. Allowed arguments: {allowed}."
        if any(_IDENTITY_ARG.search(a) for a in extra):
            message += " This assistant can only use the signed-in student's records."
        elif name == "plan_schedule" and "section_ids" in extra:
            message += (" To check specific sections, call plan_schedule with their course_ids;"
                        " it returns every valid section combination.")
        raise ToolArgumentError(message)

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
        required_preferences: list[str] | None = None,
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

        required = required_preferences or []
        if not isinstance(required, list) or any(r not in PREFERENCE_NAMES for r in required):
            raise ToolArgumentError(f"required_preferences must be a list of {list(PREFERENCE_NAMES)}.")

        stated = [k for k, v in (("earliest_start", earliest_start), ("latest_end", latest_end),
                                 ("avoid_days", days)) if v]
        corrections: list[dict] = []
        if self.check_preference_language:
            required, corrections = reconcile(self._request, stated, list(required))

        plan = await plan_schedules(
            self.tools,
            self.student_id,
            self.term_id,
            [c.strip().upper() for c in course_ids],
            Preferences(earliest_start or None, latest_end or None, tuple(days), tuple(required)),
        )
        result = plan.to_dict()
        result.pop("student_id", None)
        result["preferences_applied"] = {
            "earliest_start": earliest_start or None,
            "latest_end": latest_end or None,
            "avoid_days": days,
            "required": sorted(required),
        }
        if corrections:
            result["preference_corrections"] = corrections
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
        self._request = request
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": request},
        ]
        trace: list[TraceEntry] = []
        revised = False
        recovery = 0  # 0: none yet, 1: model was nudged, 2: system recovery used
        recoveries: list[dict] = []

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

            # --- evidence orchestration (bounded: one nudge, one system-run plan)
            missing: list[str] = []
            if self.check_evidence:
                need = required_courses(request, trace, self.student_id)
                missing = missing_plan_evidence(need, trace)
                if missing and recovery == 0:
                    recovery = 1
                    recoveries.append({"type": "nudge", "missing_course_ids": missing, "step": step})
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "user", "content": (
                        f"[System check] The student asked about taking or planning {', '.join(need['course_ids'])}, "
                        f"but no plan_schedule result covers {', '.join(missing)}. The course catalog does not "
                        "show whether a course is offered this term or whether this student can take it. "
                        f"Call plan_schedule now with course_ids {json.dumps(need['course_ids'])}, adding time or "
                        "day preferences only if the student stated them. Do not ask the student first."
                    )})
                    continue
                if missing and recovery == 1:
                    recovery = 2
                    if not has_preference_wording(request):
                        args = {"course_ids": need["course_ids"]}
                        ok, result = await self._run_tool("plan_schedule", args)
                        trace.append(TraceEntry("plan_schedule", args, ok, result, by="system"))
                        recoveries.append({"type": "system_plan_schedule", "arguments": args, "ok": ok,
                                           "step": step})
                        messages.append({"role": "assistant", "content": "", "tool_calls": [
                            {"function": {"name": "plan_schedule", "arguments": args}}]})
                        messages.append({"role": "tool", "tool_name": "plan_schedule",
                                         "content": json.dumps(result)})
                        messages.append({"role": "user", "content": (
                            "[System check] plan_schedule was run for the requested courses. Answer the "
                            "student using only this result."
                        )})
                        continue
                    recoveries.append({"type": "not_run", "reason": "request states time/day wishes; "
                                       "a plan without them would ignore the student", "step": step})
                missing = missing_plan_evidence(need, trace)

            # --- grounding: sections and availability/eligibility claims
            if self.check_evidence:
                mentions = section_mentions(answer, trace, request)
                ungrounded = mentions["ungrounded"]
                rejected = mentions["rejected_mentions"]
                claims = unsupported_claims(answer, trace)
            else:
                ungrounded = sorted(set(SECTION_ID_PATTERN.findall(answer)) - self._allowed_section_ids(trace))
                rejected, claims = [], []
            if (ungrounded or claims) and not revised:
                revised = True
                problems = []
                if ungrounded:
                    problems.append(f"it mentions section(s) {', '.join(ungrounded)} that were not in any "
                                    "plan_schedule option")
                for c in claims:
                    problems.append(f'it says "{c["sentence"]}" but {c["reason"]}')
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": (
                    "Your answer is not supported by the tool results: " + "; ".join(problems) + ". "
                    "Rewrite it using only facts from tool results, calling plan_schedule if needed. "
                    "If something cannot be checked, say so instead of stating it."
                )})
                continue

            if missing:
                answer += ("\n\n(Note: I could not check section availability for "
                           f"{', '.join(missing)} in this conversation, so nothing above confirms that you can "
                           "register for it.)")
            return AssistantResult(
                answer=answer,
                grounded=not ungrounded and not claims,
                ungrounded_section_ids=ungrounded,
                stopped_reason="answered",
                model_calls=step,
                trace=trace,
                mcp_calls=list(self.tools.calls),
                unsupported_claims=claims,
                rejected_section_mentions=rejected,
                evidence_missing=missing,
                recoveries=recoveries,
            )

        return AssistantResult(
            answer="Sorry, I couldn't finish planning this request. Please try rephrasing it.",
            grounded=True,
            ungrounded_section_ids=[],
            stopped_reason="max_steps",
            model_calls=self.max_steps,
            trace=trace,
            mcp_calls=list(self.tools.calls),
            recoveries=recoveries,
        )
