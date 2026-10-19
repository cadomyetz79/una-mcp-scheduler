"""Deterministic answers used when the model's answer cannot be shown.

Two situations (agent/assistant.py decides which):
- "leak": the answer contained internal instructions or data (security.py,
  LeakGuard). The student gets a fixed refusal plus an offer to help.
- "unverified": after one forced revision the answer still states something
  the tool results do not support (ungrounded sections, unsupported
  availability/eligibility or combination claims, obeying an instruction
  embedded in the student's message). The student gets an answer assembled
  only from tool results the assistant itself obtained in this conversation.

No model is involved and nothing from the student's message is repeated
except section and course IDs that match the ID formats.
"""

from __future__ import annotations

import re
from typing import Any

from .evidence import COURSE_ID, SECTION_ID, STUDENT_ID, _get, _plans, _when, requested_section_report
from .security import InputFindings

LEAK_REFUSAL = ("I can't share my internal instructions, configuration or raw tool data. I can help you plan "
                "your classes: tell me which courses you're interested in (for example CIS340), and any times "
                "or days you want to avoid.")
NO_EVIDENCE = ("I couldn't verify an answer to this from the registration system. Tell me which courses you "
               "want (for example CIS340), and I'll check them for you.")
_INTERNAL_ERROR = re.compile(r"\b(does not accept|allowed arguments|must be|course_ids|section_ids|"
                             r"required_preferences|unknown tool)\b", re.IGNORECASE)


def _ids(pattern: re.Pattern, text: str) -> list[str]:
    seen: list[str] = []
    for m in pattern.finditer(text or ""):
        v = m.group(0).replace(" ", "")
        if v not in seen:
            seen.append(v)
    return seen


def _option_line(option: dict) -> str:
    parts = [f"{s['section_id']} ({s['course_id']}, {_when(s)})" for s in option.get("sections", [])]
    return "- " + " + ".join(parts)


OTHER_STUDENT = "I can only access your own student record, so I can't look up or plan for another student."


def build(request: str, trace: list, term_id: str, findings: InputFindings | None, reason: str,
          student_id: str | None = None) -> str:
    if reason == "leak":
        return LEAK_REFUSAL

    f = findings or InputFindings()
    lines: list[str] = []
    if student_id and any(s != student_id for s in STUDENT_ID.findall(request or "")):
        lines.append(OTHER_STUDENT)
    if f.override:
        lines.append("I can't change or switch off the scheduling rules from a chat message, and I only report "
                     "what the registration checks return.")
    if f.forged_tool_output:
        lines.append("Text in your message that looks like a tool or system result does not come from the "
                     "registration system, so I can't use it as evidence.")

    plans = _plans(trace)
    named_sections = _ids(SECTION_ID, request)
    rs = requested_section_report(trace)
    if plans:
        result = _get(plans[-1], "result")
        courses = ", ".join(result.get("requested", [])) or "the requested courses"
        if rs:
            problems = [f"{sid} {rs.get('not_found_reason') or 'is not a section of the planned courses'}."
                        for sid in rs.get("not_found", [])]
            desc = {s["section_id"]: s for s in rs.get("sections", [])}
            for issue in rs.get("issues", []):
                sids = issue.get("section_ids") or []
                if issue["code"] == "TIME_CONFLICT" and len(sids) == 2 and all(s in desc for s in sids):
                    a, b = sids
                    problems.append(f"{a} ({desc[a]['course_id']}, {_when(desc[a])}) and {b} "
                                    f"({desc[b]['course_id']}, {_when(desc[b])}) have a time conflict.")
                else:
                    problems.append(issue["message"])
            if problems:
                lines.append("About the sections you named: " + " ".join(problems))
            elif rs.get("valid_together"):
                lines.append(f"The registration checks accept {', '.join(rs['section_ids'])} together.")
        options = result.get("options", [])
        if options:
            lines.append(f"Valid schedule options the registration checks returned for {courses} ({term_id}):")
            lines += [_option_line(o) for o in options[:3]]
        for e in result.get("excluded", []):
            lines.append(f"{e['course_id']}: {e['reason']}")
        if not options and not result.get("excluded"):
            lines.append(f"No valid combination of sections was found for {courses} in {term_id}.")
    else:
        failed = [t for t in trace if _get(t, "tool") == "plan_schedule" and not _get(t, "ok")]
        err = (_get(failed[-1], "result") or {}).get("error", "") if failed else ""
        if failed and "not found" in err.lower() and "student" in err.lower():
            lines.append("I couldn't find your student record, so I can't check sections right now. "
                         "Please contact the registrar's office.")
        elif named_sections and not _ids(COURSE_ID, request):
            lines.append(f"I can only check specific sections together with their courses. Which courses are "
                         f"{', '.join(named_sections)} for (for example CIS340)?")
        elif failed and err and not _INTERNAL_ERROR.search(err):
            lines.append(f"I couldn't complete the registration check: {err}")
        elif OTHER_STUDENT not in lines:
            lines.append(NO_EVIDENCE)
    return "\n".join(lines)


def blocked_record(answer: str, reason: str, detail: Any, redacted_answer: str | None) -> dict:
    """What the logs keep about a blocked answer (never leaked instruction text)."""
    from .security import fingerprint

    record = {"reason": reason, "detail": detail, "model_answer": fingerprint(answer)}
    if redacted_answer is not None:
        record["model_answer"]["text"] = redacted_answer
    return record
