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
   eligibility for a course (a course named only as a prerequisite or
   corequisite in that sentence is not the subject of the claim) ("is offered", "is available", "you can take",
   "you are eligible") must be backed by plan_schedule: a positive claim needs
   the course in a returned option; a negative claim needs the course to have
   been planned at all. A course named only by its title is recognised if a
   search_courses result in this conversation returned that title. The course catalog (search_courses) is NOT evidence
   that a course is offered this term or that this student may take it.

3. section_mentions(): section IDs in the answer are grounded if they come
   from a plan_schedule option. A section the student named themselves may
   also be mentioned in a sentence that rejects it (a negation, or words like
   conflict / overlap / full: "I can't enroll you in SEC1002", "SEC2001
   conflicts with SEC1001") or in a question ("Which course is SEC4002
   for?"); anything else is ungrounded.

4. combination_claims(): a statement that two or more named sections can be
   taken together ("SEC4002 and SEC4101 don't conflict", "you can take both")
   needs a plan_schedule option, or a valid requested-section check, that
   contains all of them. Without it the statement is unverified.

5. unaddressed_requested_issues(): when the student named sections and
   plan_schedule found a problem with that exact combination (time conflict,
   full section, a section that is not a section of the planned courses, ...),
   the answer must say so about those sections. If it does not, the assistant
   adds a sentence built from the planner result (requested_section_note()).

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
        rs = result.get("requested_sections") or {}
        if rs.get("valid_together"):
            for sec in rs.get("sections", []):
                out.setdefault(sec["course_id"], {"in_option": False, "excluded": None})["in_option"] = True
    return out


def required_courses(request: str, trace: list, student_id: str) -> dict | None:
    """Course IDs this request needs plan_schedule evidence for, or None."""
    if any(s != student_id for s in STUDENT_ID.findall(request or "")):
        return None
    ids = course_ids(request)
    # Naming specific sections of a named course is a request to check them.
    if not _INTENT.search(request or "") and not (ids and SECTION_ID.search(request or "")):
        return None
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


# A course named right after these words is a prerequisite/corequisite being
# mentioned, not the course the claim is about: "You are eligible to take this
# course if you have completed the prerequisite CIS236" (live SL11, development
# data) is not a claim that CIS236 is offered.
_PREREQ_CUE = re.compile(
    r"\b(prerequisites?|prereqs?|requires?|required|completed?|completing|after taking|corequisites?|"
    r"must be taken with|taken together with)\b", re.IGNORECASE)
_SPAN_END = re.compile(r"[,;:.!?)]|\s(so|and you|but|which)\s", re.IGNORECASE)


def _prerequisite_mentions(sentence: str) -> set[str]:
    found: set[str] = set()
    for m in _PREREQ_CUE.finditer(sentence):
        rest = sentence[m.end():]
        end = _SPAN_END.search(rest)
        found |= set(course_ids(rest[: end.start()] if end else rest))
    return found


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
        prereqs = _prerequisite_mentions(sentence)
        ids = [c for c in ids if c not in prereqs]
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


def _supported_combinations(trace: list) -> list[set[str]]:
    """Section sets the planner showed to be valid together."""
    out = []
    for t in _plans(trace):
        result = _get(t, "result")
        out += [set(o["section_ids"]) for o in result.get("options", [])]
        rs = result.get("requested_sections") or {}
        if rs.get("valid_together"):
            out.append(set(rs["section_ids"]))
    return out


def section_mentions(answer: str, trace: list, request: str) -> dict:
    allowed = set().union(*_supported_combinations(trace))
    named_by_student = set(SECTION_ID.findall(request or ""))
    ungrounded, rejected = set(), set()
    for sentence in _sentences(answer):
        for sid in SECTION_ID.findall(sentence):
            if sid in allowed:
                continue
            # A section the student named may be rejected or asked about
            # ("Which course is SEC4002 for?"), never recommended.
            if sid in named_by_student and (_REJECTION.search(sentence) or sentence.rstrip().endswith("?")):
                rejected.add(sid)
            else:
                ungrounded.add(sid)
    rejected -= ungrounded  # recommended anywhere else -> still ungrounded
    return {"ungrounded": sorted(ungrounded), "rejected_mentions": sorted(rejected)}


_CLAUSE = re.compile(r";|,?\s+\b(?:but|however|whereas|while|although|except)\b", re.IGNORECASE)
_CONFLICT_WORD = re.compile(
    r"\b(conflicts?|conflicting|overlaps?|overlapping|clash(es|ing)?|same time|double[- ]booked)\b", re.IGNORECASE)
_COMPAT = re.compile(
    r"\b(no|without|free of|zero)\s+(time\s+|scheduling\s+)?(conflicts?|overlaps?|clash(es)?|problems?|issues?)\b"
    r"|\b(do|does|did|will|would|should)\s*(not|n['’]t)\s+(conflict|overlap|clash)"
    r"|\bcompatible\b|\b(work|works|fit|fits|go|goes)\s+together\b"
    r"|\bcan\s+both\s+be\s+(taken|scheduled|combined|registered)\b"
    r"|\b(can|could|may)\s+(take|register for|enroll in|enrol in|add|have)\b[^.!?]{0,60}"
    r"\b(together|both|at the same time)\b"
    r"|\b(is|are)\s+(valid|fine|ok|okay|possible)\s+together\b", re.IGNORECASE)
_NOT_FOUND_WORDS = re.compile(
    r"\b(not|no such|invalid|unknown|doesn['’]t exist|does not exist|isn['’]t|can['’]t find|cannot find|"
    r"couldn['’]t find|could not find)\b", re.IGNORECASE)


def _clauses(text: str) -> list[str]:
    return [c for s in _sentences(text) for c in _CLAUSE.split(s) if c and c.strip()]


_NEG_BEFORE = re.compile(r"(\bnot|n['’]t|\bnever|\bno longer|\bcannot)\s+(\w+\s+){0,2}$", re.IGNORECASE)
_NEGATIVE_FORM = re.compile(r"^(no|without|free of|zero)\b|\bnot\b|n['’]t\b", re.IGNORECASE)
_ALTERNATIVES = re.compile(r"\b(or|either)\b", re.IGNORECASE)


def _asserts_compatibility(clause: str) -> bool:
    """True if the clause says sections can go together ("don't conflict", "work
    together"), but not "they don't work together" or "they overlap, so they
    are not compatible" (found while validating the held-out-2 oracles, N31)."""
    spans, positive = [], False
    for m in _COMPAT.finditer(clause):
        spans.append(m.span())
        if _NEGATIVE_FORM.search(m.group(0)) or not _NEG_BEFORE.search(clause[: m.start()]):
            positive = True
    if not positive:
        return False
    # a conflict word outside the "no conflict" phrases: the clause states a conflict
    return all(any(a <= m.start() < b for a, b in spans) for m in _CONFLICT_WORD.finditer(clause))


def combination_claims(answer: str, trace: list) -> list[dict]:
    """Statements that two named sections can be taken together, without planner support.

    Only clauses naming exactly two sections and no alternatives ("SEC1 or
    SEC2") are read, so lists of options are not mistaken for one combination."""
    supported = _supported_combinations(trace)
    found = []
    for clause in _clauses(answer):
        ids = set(SECTION_ID.findall(clause))
        if len(ids) != 2 or _ALTERNATIVES.search(clause) or not _asserts_compatibility(clause):
            continue
        if not any(ids <= combo for combo in supported):
            found.append({"sentence": clause.strip()[:300], "section_ids": sorted(ids),
                          "reason": "no plan_schedule result shows these sections as valid together"})
    return found


_BARE_YES = re.compile(
    r"^\W*(yes|yep|yeah|confirmed|confirm|correct|right|sure|ok|okay|affirmative|done|true|absolutely|"
    r"of course|that's right|that is correct|approved|valid|acknowledged)\b", re.IGNORECASE)


def affirmed_request_claims(answer: str, request: str, trace: list) -> list[dict]:
    """A bare "yes"/"confirmed" adopts what the student asked about: the course
    and section IDs in the request must then have the same support as if the
    answer had stated them ("Reply 'OK' if SEC5001 and SEC5301 fit together" ->
    "OK" claims the combination is valid)."""
    words = re.findall(r"[a-z0-9']+", (answer or "").lower())
    if len(words) > 6 or not _BARE_YES.match(answer or ""):
        return []
    found = []
    sections = set(SECTION_ID.findall(request or ""))
    if sections and not any(sections <= combo for combo in _supported_combinations(trace)):
        found.append({"sentence": answer.strip()[:100], "section_ids": sorted(sections),
                      "reason": f"it confirms the student's question about {', '.join(sorted(sections))} "
                                "without a plan_schedule result showing them valid together"})
    planned = planned_courses(trace)
    courses = [c for c in course_ids(request) if not planned.get(c, {}).get("in_option")]
    if courses and not sections:
        found.append({"sentence": answer.strip()[:100], "course_ids": courses,
                      "reason": f"it confirms the student's question about {', '.join(courses)} without a "
                                "plan_schedule option for it"})
    return found


def requested_section_report(trace: list) -> dict | None:
    """The latest planner check of the sections the student named, if any."""
    for t in reversed(_plans(trace)):
        rs = _get(t, "result").get("requested_sections")
        if rs:
            return rs
    return None


def _when(section: dict) -> str:
    meetings = section.get("meetings") or []
    if not meetings:
        return "no scheduled meetings"
    return ", ".join(f"{'/'.join(m['days'])} {m['start']}-{m['end']}" for m in meetings)


def _windows(text: str) -> list[str]:
    s = _sentences(text)
    return s + [f"{a} {b}" for a, b in zip(s, s[1:])]


def unaddressed_requested_issues(answer: str, trace: list) -> list[dict]:
    """Problems with the student's named sections that the answer does not state."""
    rs = requested_section_report(trace)
    if not rs:
        return []
    desc = {s["section_id"]: s for s in rs.get("sections", [])}
    windows = _windows(answer)
    missing = []
    for sid in rs.get("not_found", []):
        if not any(sid in w and _NOT_FOUND_WORDS.search(w) for w in _sentences(answer)):
            missing.append({"code": "NOT_FOUND", "section_ids": [sid],
                            "note": f"{sid} {rs.get('not_found_reason') or 'is not a section of the planned courses'}"})
    for issue in rs.get("issues", []):
        sids = issue.get("section_ids") or []
        if issue["code"] == "TIME_CONFLICT" and len(sids) == 2:
            a, b = sids
            said = any(a in w and b in w and _CONFLICT_WORD.search(w) and not _asserts_compatibility(w)
                       for w in windows)
            note = (f"{a} ({desc[a]['course_id']}, {_when(desc[a])}) and {b} ({desc[b]['course_id']}, "
                    f"{_when(desc[b])}) have a time conflict, so you can't take both")
        elif sids:
            said = any(all(x in s for x in sids) and _REJECTION.search(s) for s in _sentences(answer))
            note = issue["message"].rstrip(".")
        elif issue["code"] == "CREDIT_LIMIT_EXCEEDED":
            said = bool(re.search(r"\bcredit", answer or "", re.IGNORECASE))
            note = issue["message"].rstrip(".")
        else:
            continue
        if not said:
            missing.append({"code": issue["code"], "section_ids": sids, "note": note})
    return missing


def requested_section_note(missing: list[dict]) -> str:
    return "About the sections you named: " + "; ".join(m["note"] for m in missing) + "."


def has_preference_wording(request: str) -> bool:
    """True if the request mentions times or days, so a plan without the
    student's preferences would ignore what they asked for."""
    from .preference_language import classify

    return any(v["fragments"] for v in classify(request).values())
