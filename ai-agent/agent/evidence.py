"""Deterministic evidence rules for the assistant's final answer.

Live evaluation (2026-10-19, qwen3:8b) showed the model often ending its turn
without the tool result the answer depends on: it searched the catalog and
then said "CIS330 is offered next spring" (false), or asked the student for
details instead of planning. These rules decide, from the request and the
tool trace only, what evidence an answer needs and whether a claim in the
answer is backed by it. No model is involved.

1. required_courses(): does the request need plan_schedule evidence, and
   for which course IDs? Only when the request is about taking / planning /
   availability AND the course IDs are known without guessing: written in the
   request, or the single result of a successful search_courses call.
   Requests naming another student are skipped (a refusal is the right
   answer there).

2. unsupported_claims(): sentences in the answer that claim availability or
   eligibility for a course ("is offered", "is available", "you can take",
   "you are eligible") must be backed by plan_schedule: a positive claim needs
   the course in a returned option; a negative claim needs the course to have
   been planned at all. A course named only by its title is recognised if a
   search_courses result in this conversation returned that title. The course catalog (search_courses) is NOT evidence
   that a course is offered this term or that this student may take it.

3. section_mentions(): section IDs in the answer are grounded if they come
   from a plan_schedule option. A section the student named themselves may
   also be mentioned in a sentence that rejects it (a negation, or words like
   conflict / overlap / full: "I can't enroll you in SEC1002", "SEC2001
   conflicts with SEC1001"); anything else is ungrounded.

Limits (WORKING ASSUMPTION): English keyword rules. A rejecting sentence is
recognised by a negation word; a positive recommendation phrased with a
negation ("SEC2001 isn't bad") would be treated as a rejection.
"""

from __future__ import annotations

import re
from typing import Any

COURSE_ID = re.compile(r"\b([A-Z]{2,4})\s?(\d{3})\b")
SECTION_ID = re.compile(r"\bSEC\d+\b")
STUDENT_ID = re.compile(r"\bS\d{5}\b")

_INTENT = re.compile(
    r"\b(plan|planning|schedule|scheduling|take|taking|enroll|enrol|register|add|"
    r"sections?|offered|available|availability|put me in|sign me up|fit|want|need|like|get|"
    r"can i get|next (spring|fall|summer|term|semester))\b",
    re.IGNORECASE,
)
_CLAIM = re.compile(
    r"\b(offered|available|open seats?|eligible|qualif(y|ied)|"
    r"(can|could|may|are able to|is able to) (take|enroll|enrol|register|get into|sign up)|"
    r"can'?t (take|enroll|register)|cannot (take|enroll|register)|"
    r"not able to (take|enroll|register))\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(not|no|never|none|cannot|unable|without)\b|n't\b|n’t\b", re.IGNORECASE)
# A sentence that rejects a section: negation, or words saying it cannot be used.
_REJECTION = re.compile(
    _NEGATION.pattern + r"|\b(conflicts?|conflicting|overlaps?|overlapping|clash(es)?|full|"
    r"unavailable|invalid|closed)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def course_ids(text: str) -> list[str]:
    seen: list[str] = []
    for subject, number in COURSE_ID.findall(text or ""):
        cid = f"{subject}{number}"
        if cid not in seen:
            seen.append(cid)
    return seen


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text or "") if s and s.strip()]


def _get(entry: Any, key: str):
    return entry[key] if isinstance(entry, dict) else getattr(entry, key)


def _plans(trace: list) -> list:
    return [t for t in trace if _get(t, "tool") == "plan_schedule" and _get(t, "ok")]


def planned_courses(trace: list) -> dict[str, dict]:
    """course_id -> {"in_option": bool, "excluded": code or None} over all successful plans."""
    out: dict[str, dict] = {}
    for t in _plans(trace):
        args, result = _get(t, "arguments"), _get(t, "result")
        for cid in args.get("course_ids", []):
            out.setdefault(str(cid).strip().upper(), {"in_option": False, "excluded": None})
        for e in result.get("excluded", []):
            out.setdefault(e["course_id"], {"in_option": False, "excluded": None})["excluded"] = e["code"]
        for option in result.get("options", []):
            for sec in option.get("sections", []):
                out.setdefault(sec["course_id"], {"in_option": False, "excluded": None})["in_option"] = True
    return out


def required_courses(request: str, trace: list, student_id: str) -> dict | None:
    """Course IDs this request needs plan_schedule evidence for, or None."""
    if any(s != student_id for s in STUDENT_ID.findall(request or "")):
        return None
    if not _INTENT.search(request or ""):
        return None
    ids = course_ids(request)
    if ids:
        return {"course_ids": ids, "source": "request"}
    searches = [t for t in trace if _get(t, "tool") == "search_courses" and _get(t, "ok")]
    if searches:
        rows = _get(searches[-1], "result")
        if isinstance(rows, list) and len(rows) == 1:
            return {"course_ids": [rows[0]["course_id"]], "source": "search_courses (single result)"}
    return None


def missing_plan_evidence(need: dict | None, trace: list) -> list[str]:
    if not need:
        return []
    planned = planned_courses(trace)
    return [c for c in need["course_ids"] if c not in planned]


def _titles_from_trace(trace: list) -> dict[str, str]:
    """lower-case course title -> course ID, for courses returned by search_courses."""
    out = {}
    for t in trace:
        if _get(t, "tool") == "search_courses" and _get(t, "ok") and isinstance(_get(t, "result"), list):
            for row in _get(t, "result"):
                if row.get("title"):
                    out[row["title"].lower()] = row["course_id"]
    return out


def unsupported_claims(answer: str, trace: list) -> list[dict]:
    planned = planned_courses(trace)
    titles = _titles_from_trace(trace)
    claims = []
    for sentence in _sentences(answer):
        if not _CLAIM.search(sentence):
            continue
        ids = course_ids(sentence)
        low = sentence.lower()
        ids += [cid for title, cid in titles.items() if title in low and cid not in ids]
        if not ids:
            continue
        negative = bool(_NEGATION.search(sentence))
        if negative:
            backed = any(c in planned for c in ids)
            why = "negative availability/eligibility claim, but none of these courses was planned"
        else:
            backed = any(planned.get(c, {}).get("in_option") for c in ids)
            why = "availability/eligibility claim, but no plan_schedule option contains these courses"
        if not backed:
            claims.append({"sentence": sentence[:300], "course_ids": ids, "reason": why})
    return claims


def section_mentions(answer: str, trace: list, request: str) -> dict:
    allowed = {s for t in _plans(trace) for o in _get(t, "result").get("options", [])
               for s in o["section_ids"]}
    named_by_student = set(SECTION_ID.findall(request or ""))
    ungrounded, rejected = set(), set()
    for sentence in _sentences(answer):
        for sid in SECTION_ID.findall(sentence):
            if sid in allowed:
                continue
            if sid in named_by_student and _REJECTION.search(sentence):
                rejected.add(sid)
            else:
                ungrounded.add(sid)
    rejected -= ungrounded  # recommended anywhere else -> still ungrounded
    return {"ungrounded": sorted(ungrounded), "rejected_mentions": sorted(rejected)}


def has_preference_wording(request: str) -> bool:
    """True if the request mentions times or days, so a plan without the
    student's preferences would ignore what they asked for."""
    from .preference_language import classify

    return any(v["fragments"] for v in classify(request).values())
