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
   Requests naming another student are marked other_student (audit
   2026-10-29, F3): no nudge or system-run plan (a refusal is the right
   answer there), but a missing plan is still reported.

2. unsupported_claims(): sentences in the answer that claim availability or
   eligibility for a course (a course named only as a prerequisite or
   corequisite in that sentence is not the subject of the claim) ("is offered", "is available", "you can take",
   "you are eligible") must be backed by plan_schedule: a positive claim needs
   the course in a returned option; a negative claim needs the course to have
   been planned at all. A course named only by its title is recognised if a
   search_courses result in this conversation returned that title. The course catalog (search_courses) is NOT evidence
   that a course is offered this term or that this student may take it.
   Audit 2026-10-29: a positive claim needs EVERY course its claiming clauses
   name in an option, not just one of them (F4); and a sentence saying the
   assistant registered, enrolled or reserved something, or that a registration
   is confirmed, is always unsupported, since no tool does that (F1,
   action_claim()).

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

6. truncated_search(): a search_courses result shows at most
   MAX_SEARCH_RESULTS courses (assistant.py). When the latest search matched
   more, no successful plan_schedule came after it, and the answer does not
   give the number of matches, the assistant adds a sentence saying so and
   asking for a narrower search (search_limit_note()). Known limit: the number
   is looked for anywhere in the answer, so the same number used for something
   else ("21 credit hours" when 21 courses matched) also skips the note.

7. section_detail_claims(): meeting times, meeting days and credit hours the
   answer gives for a planned section must be the ones in the plan_schedule
   result (audit 2026-10-29, F2: "SEC5201 runs 5:00 PM - 7:50 PM" passed
   although the plan says WED 17:00-18:50). A time range must be a meeting of
   the sections the sentence names (plus the planned and current sections of
   a course it names without one of that course's sections), the student's
   own time window, or, in a sentence about a conflict, a span inside a
   meeting. A day list right before such a range, after "meets on" or after
   "Days:" (not "Avoided days:") must be days of those meetings. A credit
   number must be a course's credit hours, an option total, a credit limit or
   a number from the request, or, with "left" / "remaining" / "currently
   registered for" ... wording right around the number (not elsewhere in the
   sentence), a difference of the plan's credit numbers; for a
   course whose credit hours are unknown, only a number above every option
   total containing it is wrong. A number stated for the only course the
   sentence names ("CIS410 is 3 credits", "CIS410 (3 credits)", a "Credits:"
   item under its line) must be that course's own credit hours when they are
   known, unless that number is a total or worked out. A list item or later sentence without IDs
   belongs to the IDs of the line above it, but is only checked when it reads
   as a section detail ("Time:", "Days:", "meets", or it starts with a day or
   a clock time). Wrong details are unsupported claims (one revision, then
   the fallback answer).
   Known limits: details swapped between two sections named in one sentence,
   and day lists in preference sentences ("you wanted to avoid Fridays"), are
   not checked; locations, seats and modality are not checked.

Limits (WORKING ASSUMPTION): English keyword rules. A rejecting sentence is
recognised by a negation word; a positive recommendation phrased with a
negation ("SEC2001 isn't bad") would be treated as a rejection.
"""

from __future__ import annotations

import bisect
import re
from typing import Any

from .preference_language import expand_day_codes

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
# The assistant has no tool that registers, enrolls or reserves anything (audit
# 2026-10-29, F1), so a sentence saying it did ("I've enrolled you in SEC2002"),
# that it can, or that a registration is confirmed is never backed by a tool
# result. "You're registered for CIS376" is allowed when every course it names
# is a current registration from the latest plan_schedule result.
_ACTION_CLAIM = re.compile(
    r"\bI(?:'ve|'ll| have| will| can| could| just)?\s+(?:now\s+|already\s+|successfully\s+|also\s+)?"
    r"(?:enroll(?:ed)?|enrol(?:led)?|register(?:ed)?|sign(?:ed)?|add(?:ed)?|book(?:ed)?|reserve[d]?|"
    r"place[d]?|put)\s+you\b"
    r"|\byou(?:'re| are| have been|'ve been| were)\s+(?:now\s+|all\s+|officially\s+|successfully\s+)?"
    r"(?:enroll?ed|registered|signed up)\b"
    r"|\b(?:seat|spot|place)s?\b[^.!?]{0,40}?\b(?:is|are|has been|have been|was|were)\s+(?:now\s+)?"
    r"(?:reserved|held|secured|saved|booked)\b"
    r"|\b(?:registration|enrollment|enrolment)s?\b[^.!?]{0,30}?\b(?:is|are|has been|have been|was|were)\s+"
    r"(?:now\s+)?(?:confirmed|complete|completed|successful|finali[sz]ed|submitted|processed)\b"
    r"|\b(?:registration|enrollment|enrolment)\s+(?:confirmed|complete|completed|successful)\b",
    re.IGNORECASE)
# "Once you're registered, ..." describes a future step, not a completed one.
_HYPOTHETICAL_BEFORE = re.compile(
    r"\b(once|after|when|whenever|if|until|unless|before|so that|to get|to be)\b[^.!?]{0,40}$", re.IGNORECASE)
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


def _search_rows(result: Any) -> tuple[list, int]:
    """(rows shown, total matches) of a search_courses result: the capped dict
    {"courses", "total_matches", "truncated"} (M1), or the plain list of rows in
    traces saved before it."""
    if isinstance(result, dict) and isinstance(result.get("courses"), list):
        total = result.get("total_matches")
        return result["courses"], total if isinstance(total, int) else len(result["courses"])
    if isinstance(result, list):
        return result, len(result)
    return [], 0


def _searches(trace: list) -> list:
    return [t for t in trace if _get(t, "tool") == "search_courses" and _get(t, "ok")]


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
    """Course IDs this request needs plan_schedule evidence for, or None.

    A request that names another student still needs the evidence (audit
    2026-10-29, F3: before, any other student ID turned the check off, so
    "Can I take CIS450? My friend S99999 liked it." was answered unchecked).
    It is marked other_student: the assistant then neither nudges the model
    nor plans by itself, so a refusal is not turned into a plan, but an answer
    without the evidence still gets the "could not check" note."""
    other_student = any(s != student_id for s in STUDENT_ID.findall(request or ""))
    need = _required_courses(request, trace)
    if need and other_student:
        need["other_student"] = True
    return need


def _required_courses(request: str, trace: list) -> dict | None:
    ids = course_ids(request)
    # Naming specific sections of a named course is a request to check them.
    if not _INTENT.search(request or "") and not (ids and SECTION_ID.search(request or "")):
        return None
    if ids:
        return {"course_ids": ids, "source": "request"}
    searches = _searches(trace)
    if searches:
        # one match in the whole catalog, not one row of a capped result
        rows, total = _search_rows(_get(searches[-1], "result"))
        if total == 1 and len(rows) == 1:
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
    for t in _searches(trace):
        for row in _search_rows(_get(t, "result"))[0]:
            if row.get("title"):
                out[row["title"].lower()] = row["course_id"]
    return out


def truncated_search(trace: list) -> dict | None:
    """The latest successful search, if it showed only part of its matches (M1)
    and no successful plan_schedule came after it (the answer is then a plan)."""
    last = max((i for i, t in enumerate(trace) if _searches([t])), default=None)
    if last is None or _plans(trace[last + 1:]):
        return None
    rows, total = _search_rows(_get(trace[last], "result"))
    return {"shown": len(rows), "total_matches": total} if total > len(rows) else None


def search_limit_note(answer: str, cut: dict | None) -> str | None:
    """A sentence telling the student that more courses matched, unless the
    answer already gives the number of matches."""
    if not cut or re.search(rf"\b{cut['total_matches']}\b", answer or ""):
        return None
    return (f"(Note: the course search found {cut['total_matches']} matching courses and only "
            f"{cut['shown']} are shown. Tell me a more specific topic or subject to narrow it down.)")


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


def _registered_courses(trace: list) -> set[str]:
    """Courses the student is registered in this term, from the latest plan_schedule result."""
    result = _latest_plan(trace) or {}
    return ({s.get("course_id") for s in result.get("current_registrations") or []}
            | {a.get("course_id") for a in result.get("already_registered") or []})


def action_claim(sentence: str, registered: set[str]) -> bool:
    """True if the sentence says a registration, enrollment or reservation was
    (or can be) made by the assistant, or is confirmed (F1)."""
    for m in _ACTION_CLAIM.finditer(sentence):
        before = sentence[: m.start()]
        if _NEG_BEFORE.search(before) or _HYPOTHETICAL_BEFORE.search(before):
            continue
        named = set(course_ids(sentence))
        if m.group(0).lower().startswith("you") and named and named <= registered:
            continue  # a current registration, stated as such
        return True
    return False


def unsupported_claims(answer: str, trace: list) -> list[dict]:
    planned = planned_courses(trace)
    titles = _titles_from_trace(trace)
    registered = _registered_courses(trace)
    claims = []
    for sentence in _sentences(answer):
        if action_claim(sentence, registered):
            claims.append({"sentence": sentence[:300], "course_ids": course_ids(sentence),
                           "reason": "the assistant cannot register, enroll or reserve, so no tool result "
                                     "shows that this happened"})
            continue
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
            # Every course a claiming clause names must be in an option (F4): one
            # planned course no longer backs "CIS410 and CIS450 are both available".
            claiming = " ".join(c for c in _CLAUSE.split(sentence) if c and _CLAIM.search(c))
            in_claim = set(course_ids(claiming)) | {cid for title, cid in titles.items()
                                                     if title in claiming.lower()}
            subjects = [c for c in ids if c in in_claim] or ids
            backed = all(planned.get(c, {}).get("in_option") for c in subjects)
            why = "availability/eligibility claim, but no plan_schedule option contains these courses"
        if not backed:
            claims.append({"sentence": sentence[:300], "course_ids": ids, "reason": why})
    return claims


def _supported_combinations(trace: list, fits_current: bool = False) -> list[set[str]]:
    """Section sets the planner showed to be valid together. fits_current=True
    keeps only sets that also need no change to current registrations (or whose
    registrations could not be checked, which the answer then says)."""
    out = []
    for t in _plans(trace):
        result = _get(t, "result")
        out += [set(o["section_ids"]) for o in result.get("options", [])
                if not fits_current or o.get("compatible_with_current_registration") is not False]
        rs = result.get("requested_sections") or {}
        if rs.get("valid_together") and not (fits_current and rs.get("fits_current_registration") is False):
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
    if sections and not any(sections <= combo for combo in _supported_combinations(trace, fits_current=True)):
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
    for issue in rs.get("issues", []) + (rs.get("registration_issues") or []):
        sids = issue.get("section_ids") or []
        if issue["code"] in ("SWITCHES_CURRENT_SECTION", "CONFLICTS_WITH_CURRENT_REGISTRATION",
                             "CREDIT_LIMIT_WITH_CURRENT"):
            said = any(all(x in s for x in sids) and (_REG_PROBLEM.search(s) or _REJECTION.search(s))
                       for s in _sentences(answer))
            note = issue["message"].rstrip(".")
        elif issue["code"] == "TIME_CONFLICT" and len(sids) == 2:
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


NOT_CHECKED_NOTE = ("Note: I couldn't check the classes you're already registered for this term, so none of these "
                    "options is confirmed to fit with them. Please check for overlaps before you register.")


def _latest_plan(trace: list) -> dict | None:
    plans = _plans(trace)
    return _get(plans[-1], "result") if plans else None


def option_label(option: dict) -> str:
    return " + ".join(option.get("section_ids") or [])


def option_change_reasons(option: dict, current: dict[str, dict]) -> list[str]:
    """Why an option needs a change to the student's current registrations
    (fixed phrases; current classes by course and meeting time)."""
    reg = option.get("current_registration") or {}
    reasons = [f"changes your current {cid} section" for cid in reg.get("switches_section_of", [])]
    for c in reg.get("conflicts", []):
        cur = current.get(c["current_course_id"])
        when = f", {_when(cur)}" if cur else ""
        reasons.append(f"{c['section_id']} overlaps your current {c['current_course_id']} class{when}")
    if reg.get("exceeds_credit_limit"):
        reasons.append(f"brings you to {reg.get('credit_hours_with_current')} credit hours with your current "
                       f"classes, over your limit of {reg.get('credit_limit')}")
    return reasons


def registration_notes(trace: list, per_option: bool = True) -> list[str]:
    """Fixed sentences about the student's current registrations, from the
    latest plan_schedule result (integration audit 2026-10-19; reviewed in
    the quality pass of 2026-10-20).

    Options that need a change to current registrations (another section of
    a registered course, an overlap with a current class, the credit limit
    together with current classes) are kept but ranked last by the planner
    (removing them is an open team decision). The notes keep the two groups
    apart: options that fit, and options that would require changing current
    registrations, with the reason. If the backend could not list
    registrations, the student is told that no option is confirmed to fit.
    per_option=False leaves out the per-option lines (the fallback answer
    labels each option itself)."""
    result = _latest_plan(trace)
    if not result:
        return []
    options = result.get("options") or []
    if not (options or result.get("requested_sections")):
        return []
    checked = result.get("current_registrations_checked")
    if checked is False:
        return [NOT_CHECKED_NOTE]
    if not checked:
        return []
    notes = []
    current = {s["course_id"]: s for s in result.get("current_registrations") or []}
    for a in result.get("already_registered") or []:
        notes.append(f"Note: you're already registered for {a['course_id']} this term "
                     f"({_when(a.get('current_section') or {})}).")
    change = [o for o in options if o.get("compatible_with_current_registration") is False]
    unconfirmed = [o for o in options if o.get("compatible_with_current_registration") is None]
    fits = [o for o in options if o.get("compatible_with_current_registration") is True]
    if per_option and change:
        if fits:
            notes.append("Note: these options fit with the classes you're already registered for: "
                         + "; ".join(option_label(o) for o in fits) + ".")
        else:
            notes.append("Note: none of these options fits with the classes you're already registered for "
                         "without a change.")
        for o in change:
            notes.append(f"Note: {option_label(o)} would require changing your current registration: "
                         + "; ".join(option_change_reasons(o, current)) + ".")
    if unconfirmed:
        notes.append("Note: I couldn't confirm your credit hours together with your current classes for "
                     + "; ".join(option_label(o) for o in unconfirmed) + ".")
    return notes


# A sentence that tells the student a section needs a change to current
# registrations: a problem word that is not negated ("overlaps your CIS376
# class", "means switching your CIS376 section"; not "no overlap"), a misfit
# ("doesn't fit with your current classes"), or a rejection ("you can't take").
_REG_PROBLEM = re.compile(
    r"\b(overlaps?|overlapping|conflicts?|conflicting|clash(es)?|switch(es|ing)?|swap(ping)?|drop(ping)?|"
    r"chang(e|es|ed|ing) (your |the |a )?(current |existing )?(registration|registrations|section|sections|"
    r"schedule|class|classes)|requires? (a )?change|would (require|mean) (a )?chang\w*|incompatible|"
    r"credit[- ]hour limit|credit limit|over (your|the) (credit[- ]hour )?limit|too many credits)\b",
    re.IGNORECASE)
_REG_NEGATED = re.compile(r"(\b(no|not|never|without|zero)|n['’]t)\s+(\w+\s+){0,2}$", re.IGNORECASE)
_REG_MISFIT = re.compile(
    r"(\b(not|never)|n['’]t)\s+(\w+\s+){0,1}(fit|fits|work|works|compatible)\b"
    r"|\b(can['’]?t|cannot|can not|shouldn['’]t|should not)\s+(\w+\s+){0,2}(take|use|add|register|pick|choose)\b",
    re.IGNORECASE)
# "fits your current schedule", "no conflict with your registered classes", ...
_REG_SAFE = re.compile(
    r"\b(fits?|fitting|works?|compatible|no (time )?(conflicts?|overlaps?|clash(es)?)|"
    r"(won['’]t|doesn['’]t|don['’]t|does not|do not|will not) (conflict|overlap|clash))\b[^.!?]{0,50}"
    r"\b(current|existing|registered|enrolled|already)\b", re.IGNORECASE)


def _states_registration_problem(sentence: str) -> bool:
    if _REG_MISFIT.search(sentence):
        return True
    return any(not _REG_NEGATED.search(sentence[: m.start()]) for m in _REG_PROBLEM.finditer(sentence))


def registration_claims(answer: str, trace: list) -> list[dict]:
    """Sentences that present an option as fine for the student's current
    registrations when the planner says it is not, or when registrations could
    not be checked (quality pass 2026-10-20). An option that would require a
    change may be mentioned, but the same sentence must say there is a problem
    (overlap, switching sections, credit limit, "doesn't fit", ...) or reject
    it; "no overlap" or "fits your current schedule" does not count.""" 
    result = _latest_plan(trace)
    if not result:
        return []
    checked = result.get("current_registrations_checked")
    options = result.get("options") or []
    found = []
    if checked:
        ok_ids = {sid for o in options if o.get("compatible_with_current_registration") is True
                  for sid in o["section_ids"]}
        change_ids = {sid for o in options if o.get("compatible_with_current_registration") is False
                      for sid in o["section_ids"]} - ok_ids
        unconfirmed_ids = {sid for o in options if o.get("compatible_with_current_registration") is None
                           for sid in o["section_ids"]} - ok_ids - change_ids
        rs = result.get("requested_sections") or {}
        for issue in rs.get("registration_issues") or []:
            change_ids |= set(issue.get("section_ids") or [])
        if rs.get("fits_current_registration") is None:
            unconfirmed_ids |= set(rs.get("section_ids") or []) - change_ids
        any_doubt = bool(change_ids or unconfirmed_ids)
        for sentence in _sentences(answer):
            ids = set(SECTION_ID.findall(sentence))
            bad = sorted(ids & change_ids)
            safe = (m := _REG_SAFE.search(sentence)) and not _NEG_BEFORE.search(sentence[: m.start()])
            if bad and not _states_registration_problem(sentence):
                found.append({"sentence": sentence[:300], "section_ids": bad,
                              "reason": f"{', '.join(bad)} would require changing the student's current "
                                        "registrations, but the sentence does not say so"})
            elif safe and ids & unconfirmed_ids:
                found.append({"sentence": sentence[:300], "section_ids": sorted(ids & unconfirmed_ids),
                              "reason": "it says sections fit the student's current registrations, but that "
                                        "could not be confirmed"})
            elif safe and any_doubt and not ids:
                found.append({"sentence": sentence[:300], "section_ids": [],
                              "reason": "it says the options fit the student's current registrations, but some "
                                        "would require a change or could not be confirmed"})
    elif checked is False:
        for sentence in _sentences(answer):
            m = _REG_SAFE.search(sentence)
            if m and not _NEG_BEFORE.search(sentence[: m.start()]):
                found.append({"sentence": sentence[:300], "section_ids": sorted(set(SECTION_ID.findall(sentence))),
                              "reason": "it says sections fit the student's current registrations, but they could "
                                        "not be checked"})
    return found


def has_preference_wording(request: str) -> bool:
    """True if the request mentions times or days, so a plan without the
    student's preferences would ignore what they asked for."""
    from .preference_language import classify

    return any(v["fragments"] for v in classify(request).values())


# --- 7. section details (F2): meeting days, times and credit hours in the answer

_DAY_CODE = {"mon": "MON", "tue": "TUE", "wed": "WED", "thu": "THU", "fri": "FRI", "sat": "SAT", "sun": "SUN"}
_DAY_WORD = (r"(?:mon(?:days?)?|tue(?:s(?:days?)?)?|tuesdays?|wed(?:nesdays?)?|thu(?:r(?:s(?:days?)?)?)?|thursdays?|"
             r"fri(?:days?)?|sat(?:urdays?)?|sun(?:days?)?)")
_DAY_LIST = re.compile(rf"\b{_DAY_WORD}\b(?:\s*(?:,|/|&|\band\b)\s*(?:and\s+)?\b{_DAY_WORD}\b)*", re.IGNORECASE)
_CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*(?:m\b\.?)?"
_RANGE = re.compile(rf"(?<![\w:]){_CLOCK}\s*(?:-|–|—|to|until)\s*{_CLOCK}(?![\w:])", re.IGNORECASE)
# a day list that directly governs a range: "Monday and Wednesday, 9:30 AM - 10:45 AM",
# "TUE/THU 09:30-10:45", "on Mon/Wed from 9:30 to 10:45"
_BRIDGE = re.compile(r"^[\s,(*:]*(?:from\s+|at\s+|between\s+)?[\s*]*$", re.IGNORECASE)
_MEETS = re.compile(r"\b(?:meets?|meeting|held)\s+(?:only\s+)?(?:on\s+|every\s+)?(?=\S)", re.IGNORECASE)
_DAYS_LABEL = re.compile(r"\bdays?\**\s*:\**\s*", re.IGNORECASE)
_CREDITS = re.compile(r"\b(\d{1,2})\s*(?:-\s*)?(?:credit(?:\s*hours?|s)?|cr\.?\s*hrs?|hours? of credit)\b"
                      r"|\bcredit(?:\s*hours?|s)?\s*(?:[:=]|of|total(?:s|ing)?|is|are)?\s*\**\s*(\d{1,2})\b",
                      re.IGNORECASE)
_MERIDIEM = re.compile(r"\b([ap])\.m\.", re.IGNORECASE)
_DETAIL_CONFLICT = re.compile(r"\b(conflicts?|conflicting|overlaps?|overlapping|clash(es|ing)?)\b", re.IGNORECASE)
_SUB_ITEM = re.compile(r"^[ \t]*(?:[-*•]|\d+[.)])\s")
# a unit that only inherited its IDs is a section detail when it is labelled ("Time:", "Days:",
# "meets") or starts with a day or a clock time ("- Monday, 9:30 AM", "  - 9:00 AM - 10:15 AM")
_DETAIL_LABEL = re.compile(r"\b(?:times?|days?|schedule|credits?|credit\s+hours)\**\s*:|\b(?:meets?|held)\b",
                           re.IGNORECASE)
_DETAIL_START = re.compile(rf"^[\s>*•#-]*(?:\d+[.)]\s+)?\**\s*(?:{_DAY_WORD}\b|\d{{1,2}}(?::\d{{2}}|\s*[ap]m\b))",
                           re.IGNORECASE)
# wording right around a credit number that works it out from the plan's numbers: after it
# ("12 credits left", "8 credit hours remaining", "12 credits of room") or before it
# ("currently registered for 4 credit hours", "Remaining credit hours: 8"); a word elsewhere in
# the sentence ("... and has seats available") does not count
_ARITHMETIC_AFTER = re.compile(
    r"\s*(?:left|remaining|remain|more|available|to\s+spare|of\s+room|under|below)\b", re.IGNORECASE)
_ARITHMETIC_BEFORE = re.compile(
    r"\b(?:currently|already|remaining|unused|room\s+for|up\s+to|registered\s+for|enrolled\s+in)\b[\w ]{0,24}$",
    re.IGNORECASE)
# a schedule total right around a credit number: "6 credit hours in total", "brings your total to 10"
_TOTAL_AFTER = re.compile(r"\s*(?:in\s+)?(?:total|altogether|combined|together)\b", re.IGNORECASE)
_TOTAL_BEFORE = re.compile(r"\b(?:total(?:s|ing)?|altogether|combined|together)\b[\w :*]{0,16}$", re.IGNORECASE)
# the one course or section a credit number directly follows (see _credit_course)
_CREDIT_OF = re.compile(
    r"\b(SEC\d+|[A-Z]{2,4}\s?\d{3})\b\**(?:\s*\(\s*(?:SEC\d+|[A-Z]{2,4}\s?\d{3})\s*\))?\**"
    r"(?:\s*\(\s*|\s*,\s*|\s*[-–—:]\s*|\s+(?:is|are|has|carries|is\s+worth|worth|counts\s+for)\s+(?:an?\s+)?)$")
# "Avoided days: Friday" is a preference, not the section's days
_PREFERENCE_BEFORE = re.compile(
    r"\b(?:avoid(?:ed|ing)?|prefer(?:red|s)?|free|off|blocked|unavailable|requested|wanted)\s*\**\s*$", re.IGNORECASE)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _field(entry: Any, key: str):
    return entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)


def _ok_calls(trace: list, tool: str) -> list:
    return [t for t in trace if _field(t, "tool") == tool and _field(t, "ok")]


def _minutes(hour: str, minute: str | None, meridiem: str | None) -> set[int]:
    """Minutes after midnight a clock time can mean: "9:30" is 09:30 or 21:30."""
    h, m = int(hour), int(minute or 0)
    if h > 24 or m > 59:
        return set()
    if meridiem:
        if h > 12:
            return set()
        return {(h % 12 + (12 if meridiem.lower() == "p" else 0)) * 60 + m}
    if h == 0 or h >= 13:
        return {h * 60 + m}
    return {h * 60 + m, (h % 12 + 12) * 60 + m if h != 12 else m}


def _ranges(text: str, bare: bool = False):
    """(match, start minutes, end minutes) of each time range. Without bare,
    a range needs a colon or AM/PM ("3-4" is not a time)."""
    for m in _RANGE.finditer(text):
        h1, m1, a1, h2, m2, a2 = m.groups()
        if not (m1 or a1 or m2 or a2 or bare):
            continue
        if not a1 and a2:
            # "6:00-7:15 PM": the end's AM/PM also applies to the start, unless
            # the range crosses noon ("11:00-12:15 PM")
            a1 = a2 if int(h1) <= int(h2) and int(h2) != 12 else None
        yield m, _minutes(h1, m1, a1), _minutes(h2, m2, a2)


def _day_codes(text: str) -> set[str]:
    return {_DAY_CODE[t.lower()[:3]] for t in re.findall(_DAY_WORD, text, re.IGNORECASE)}


def _hhmm(value: Any) -> int | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value) if isinstance(value, str) else None
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _plan_results(trace: list) -> list[dict]:
    return [r for t in _ok_calls(trace, "plan_schedule") if isinstance(r := _field(t, "result"), dict)]


def _plan_options(trace: list) -> list[dict]:
    return [o for r in _plan_results(trace) for o in _as_list(r.get("options")) if isinstance(o, dict)]


def _option_courses(option: dict) -> set[str]:
    return {s["course_id"] for s in _as_list(option.get("sections"))
            if isinstance(s, dict) and isinstance(s.get("course_id"), str) and s["course_id"]}


def _described_sections(trace: list):
    """(key, course_id, meetings) of every section a plan_schedule result
    describes; meetings are (days, start, end) in minutes. Current
    registrations come without a section ID (_hide_current_section_ids in
    assistant.py), so they are keyed by course."""
    for result in _plan_results(trace):
        rows = [s for o in _as_list(result.get("options")) if isinstance(o, dict) for s in _as_list(o.get("sections"))]
        rows += [dict(s, section_id=None) for s in _as_list(result.get("current_registrations")) if isinstance(s, dict)]
        requested = result.get("requested_sections")
        rows += _as_list(requested.get("sections")) if isinstance(requested, dict) else []
        for s in rows:
            if not isinstance(s, dict) or not isinstance(s.get("course_id"), str) or not s["course_id"]:
                continue
            if s.get("section_id") is not None and not isinstance(s["section_id"], str):
                continue
            meetings = []
            for m in _as_list(s.get("meetings")):
                if not isinstance(m, dict):
                    continue
                start, end = _hhmm(m.get("start")), _hhmm(m.get("end"))
                days = [m["days"]] if isinstance(m.get("days"), str) else _as_list(m.get("days"))
                if start is not None and end is not None:
                    meetings.append(({str(d).upper()[:3] for d in days}, start, end))
            yield s.get("section_id") or f"current {s['course_id']}", s["course_id"], meetings


def _course_credits(trace: list) -> dict[str, int]:
    """course_id -> credit hours, from search_courses rows and plan option
    totals (a one-course option, or one where every other course is known)."""
    known = {r["course_id"]: r["credit_hours"] for t in _ok_calls(trace, "search_courses")
             for r in _search_rows(_field(t, "result"))[0]
             if isinstance(r, dict) and isinstance(r.get("course_id"), str) and r["course_id"]
             and isinstance(r.get("credit_hours"), int)}
    options = [(o, _option_courses(o)) for o in _plan_options(trace) if isinstance(o.get("total_credit_hours"), int)]
    changed = True
    while changed:
        changed = False
        for o, cids in options:
            unknown = cids - set(known)
            if len(unknown) == 1:
                course = next(iter(unknown))
                value = o["total_credit_hours"] - sum(known[c] for c in cids if c != course)
                if value > 0:  # contradictory data derives nothing
                    known[course] = value
                    changed = True
    return known


def _credit_values(trace: list, request: str, known: dict[str, int]) -> tuple[set[int], set[int]]:
    """(credit-hour numbers the trace or the request backs, differences an
    answer may work out from them: "12 credit hours left under your limit",
    "you are registered for 3 credit hours"). The differences are accepted
    only for a number with _ARITHMETIC_AFTER / _ARITHMETIC_BEFORE wording."""
    values: set = set(known.values())
    derived: set = set()
    record_max = [r.get("max_credit_hours") for t in _ok_calls(trace, "get_my_record")
                  if isinstance(r := _field(t, "result"), dict)]
    values |= set(record_max)
    for result in _plan_results(trace):
        for o in _as_list(result.get("options")):
            if not isinstance(o, dict):
                continue
            total = o.get("total_credit_hours")
            values.add(total)
            current = o.get("current_registration")
            if isinstance(current, dict):
                now, limit = current.get("credit_hours_with_current"), current.get("credit_limit")
                values |= {now, limit}
                for a, b in [(limit, now), (now, total), (limit, total)] + [(mx, now) for mx in record_max]:
                    if isinstance(a, int) and isinstance(b, int) and a > b:
                        derived.add(a - b)
        requested = result.get("requested_sections")
        if isinstance(requested, dict):
            for issue in _as_list(requested.get("issues")) + _as_list(requested.get("registration_issues")):
                message = str(issue.get("message", "")) if isinstance(issue, dict) else ""
                values |= {int(n) for n in re.findall(r"\b(\d{1,2}) credit", message)}
    values |= {int(n) for n in re.findall(r"\b(\d{1,2})\b", request or "")}
    return {v for v in values if isinstance(v, int)}, derived


def _credit_course(sentence: str, match: re.Match, has_own_ids: bool, section_course: dict[str, str]) -> str | None:
    """The course a _CREDITS number is stated for: the course (or section)
    right before it ("CIS410 is 3 credits", "CIS410 (3 credits)", "SEC2002
    (CIS410, 3 credits)"), "" for a "Credits: 3" item under a section line, or
    None when the number is not tied to one course."""
    if match.group(2) is not None:  # "Credits: 3"
        lead = sentence[:match.start()]
        return "" if not has_own_ids and re.fullmatch(r"[\s>*•#-]*\**\s*", lead) else None
    m = _CREDIT_OF.search(sentence, max(0, match.start() - 60), match.start())
    if not m:
        return None
    cid = re.sub(r"\s", "", m.group(1))
    return section_course.get(cid, cid)


def _detail_units(answer: str):
    """(sentence, inherited IDs): a list item without IDs of its own
    ("   - Time: 9:30 AM - 10:45 AM") gets the IDs of the line it belongs to,
    and later sentences of a line get the IDs the line named.
    section_detail_claims() checks a unit that only inherited its IDs when it
    reads as a section detail (_DETAIL_LABEL, _DETAIL_START)."""
    text = _MERIDIEM.sub(lambda m: m.group(1) + "m", answer or "")
    owner: list[str] = []
    for line in text.split("\n"):
        ids = SECTION_ID.findall(line) + course_ids(line)
        if ids:
            owner = ids
        elif not _SUB_ITEM.match(line):
            owner = []
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if sentence.strip():
                yield sentence.strip(), owner


def section_detail_claims(answer: str, trace: list, request: str = "") -> list[dict]:
    meetings: dict[str, list] = {}
    by_course: dict[str, list[str]] = {}
    section_course: dict[str, str] = {}
    for key, cid, mts in _described_sections(trace):
        meetings[key] = mts
        section_course[key] = cid
        by_course.setdefault(cid, []).append(key)
    if not meetings:
        return []
    known_credits = _course_credits(trace)
    credits, derived_credits = _credit_values(trace, request, known_credits)
    options = [(o.get("total_credit_hours"), _option_courses(o)) for o in _plan_options(trace)]
    planned: set[str] = set()
    # the student's own window ("fits your 10:00-17:00 window"): from the request or the plan arguments
    windows = [(a, b) for _, a, b in _ranges(expand_day_codes(request or ""), bare=True)]
    for t in _ok_calls(trace, "plan_schedule"):
        args = _field(t, "arguments")
        if isinstance(args, dict):
            planned |= {str(c).upper() for c in _as_list(args.get("course_ids"))}
            a, b = _hhmm(args.get("earliest_start")), _hhmm(args.get("latest_end"))
            if a is not None and b is not None:
                windows.append(({a}, {b}))
    found = []
    for raw, inherited in _detail_units(answer):
        sentence = expand_day_codes(raw)
        own = SECTION_ID.findall(sentence) + course_ids(sentence)
        if not own and not (_DETAIL_LABEL.search(sentence) or _DETAIL_START.match(sentence)):
            inherited = []  # "- Lunch is free from 12:00 PM - 1:00 PM" under a section line
        # each ID once: a line repeating an ID must not multiply the meetings compared
        ids = list(dict.fromkeys(own + inherited))
        named = [s for s in ids if s in meetings]
        # a course named without one of its sections: its planned and current sections
        # ("SEC2001 conflicts with your CIS376 class, MON/WED 9:30-10:45"); a course whose
        # section is named is that section only ("CIS410 (SEC2002)")
        covered = {section_course[s] for s in named}
        named = list(dict.fromkeys(named + [s for c in ids if c not in covered for s in by_course.get(c, [])]))
        wrong = []
        if named:
            mts = [mt for s in named for mt in meetings[s]]
            by_end = {d.end(): d for d in _DAY_LIST.finditer(sentence)}
            list_ends = sorted(by_end)
            conflict = bool(_DETAIL_CONFLICT.search(sentence))
            for m, starts, ends in _ranges(sentence):
                if any(starts & a and ends & b for a, b in windows):
                    continue
                hit = [d for d, a, b in mts if a in starts and b in ends]
                if not hit and conflict:
                    # "they overlap from 10:30 to 10:45": a span inside a meeting
                    hit = [d for d, a, b in mts if any(a <= s < e <= b for s in starts for e in ends)]
                if not hit:
                    wrong.append(f"time {m.group(0).strip()}")
                    continue
                # the first day list ending at most 20 characters before the range
                i = bisect.bisect_left(list_ends, m.start() - 20)
                dl = by_end[list_ends[i]] if i < len(list_ends) and list_ends[i] <= m.start() else None
                if (dl and _BRIDGE.match(sentence[dl.end():m.start()])
                        and not _day_codes(dl.group(0)) <= set().union(*hit)):
                    wrong.append(f"days {dl.group(0)} at {m.group(0).strip()}")
            all_days = set().union(*(mt[0] for mt in mts))
            labels = [c for c in _DAYS_LABEL.finditer(sentence)
                      if not _PREFERENCE_BEFORE.search(sentence, max(0, c.start() - 40), c.start())]
            for cue in list(_MEETS.finditer(sentence)) + labels:
                d = _DAY_LIST.match(sentence, cue.end())
                if d and not _day_codes(d.group(0)) <= all_days:
                    wrong.append(f"days {d.group(0)}")
        if credits and (named or set(ids) & planned or re.search(r"\btotal\b", sentence, re.IGNORECASE)):
            courses = {c for c in ids if c in planned} | {section_course.get(s) for s in named} - {None}
            # a course with unknown credit hours: only a number above every
            # option total that contains it is wrong ("SEC2002 is 9 credit hours")
            unknown = not courses <= set(known_credits)
            ceiling = max((total for total, cids in options if isinstance(total, int) and courses & cids), default=0)
            # one course named, with known credit hours: a number stated for that course must be
            # its own credit hours ("CIS410 is 6 credits"), unless the number is a total or worked out
            stated = {section_course.get(s) for s in named} | {c for c in ids if c in known_credits or c in planned
                                                               or c in by_course}
            stated.discard(None)
            course = next(iter(stated)) if len(stated) == 1 else None
            own_credits = known_credits.get(course) if course else None
            for c in _CREDITS.finditer(sentence):
                n = int(c.group(1) or c.group(2))
                before = max(0, c.start() - 40)
                arithmetic = bool(_ARITHMETIC_AFTER.match(sentence, c.end())
                                  or _ARITHMETIC_BEFORE.search(sentence, before, c.start()))
                total = bool(_TOTAL_AFTER.match(sentence, c.end()) or _TOTAL_BEFORE.search(sentence, before, c.start()))
                backed = credits | derived_credits if arithmetic else credits
                if n not in backed and (not unknown or (ceiling and n > ceiling)):
                    wrong.append(f"{n} credit hours")
                elif own_credits is not None and not arithmetic and not total and n != own_credits and _credit_course(
                        sentence, c, bool(own), section_course) in ("", course):
                    wrong.append(f"{n} credit hours for {course}")
        if wrong:
            found.append({"sentence": raw[:300], "section_ids": sorted(set(named)), "details": sorted(set(wrong)),
                          "reason": "the meeting days, times or credit hours it gives for these sections are not "
                                    "the ones in the plan_schedule result"})
    return found
