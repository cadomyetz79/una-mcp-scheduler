"""Answer-level assertions for scoring v2 (evaluation only).

Written separately from agent/evidence.py on purpose: the system's own
runtime rules must not grade themselves. Nothing here is imported by the
assistant.

Why v2: in the live development runs, E14 passed scoring v1 because its
keyword group ["overlap", "conflict", ...] matched "has no conflicts", although
the answer never said which requested section conflicted. v2 checks
statements about specific sections and courses at sentence level:

- conflict(a, b): a and b both appear within a two-sentence window that
  contains a conflict word ("conflict", "overlap", "clash", "same time");
  a window whose conflict word is negated ("no conflicts", "don't overlap")
  does not count.
- availability(course): "not_offered" needs a sentence saying the course is
  not offered / has no sections and no sentence saying it is; "offered" the
  reverse (or one of its sections named).
- ineligible(course, missing): the course and a missing prerequisite appear
  within a two-sentence window with requirement wording.
- clarification: the answer asks a question (and names enough candidates).
- sections_ok: every section ID in the answer is an allowed option section,
  or one the student named, mentioned in a rejecting sentence.
- false_claims: availability/eligibility statements compared with the TRUTH
  computed from the dataset (independent of what tools were called).
- unsupported_claims: positive availability/eligibility statements that no
  successful plan_schedule in the trace supports.
"""

from __future__ import annotations

import re

COURSE = re.compile(r"\b([A-Z]{2,4})\s?(\d{3})\b")
SECTION = re.compile(r"\bSEC\d+\b")
NEG = re.compile(r"\b(not|no|never|none|cannot|unable|without|neither|nor)\b|n['’]t\b", re.I)
CONFLICT = re.compile(r"\b(conflicts?|conflicting|overlaps?|overlapping|clash(es|ing)?|same time|double[- ]booked)\b", re.I)
NO_CONFLICT = re.compile(
    r"\b(no|without|free of|zero)\s+(time\s+)?(conflicts?|overlaps?|clash(es)?)\b|conflict[- ]free"
    r"|\b(do|does|did|will|would)\s*(not|n['’]t)\s+(conflict|overlap|clash)", re.I)
REJECT = re.compile(NEG.pattern + r"|" + CONFLICT.pattern + r"|\b(full|unavailable|invalid|closed|instead)\b", re.I)
NOT_OFFERED = re.compile(
    r"\b(not|isn['’]t|aren['’]t|won['’]t be|will not be)\s+(being\s+)?(offered|available|scheduled)\b"
    # "no section" counts only when it is not narrowed by a condition:
    # "no open section that starts at 10am" / "no section off Mondays" are about
    # preferences, not about the course being offered.
    r"|\bno\s+(open\s+)?sections?\b(?!\s+(that|which|at|on|off|after|before|starting|fits?|matching|meeting|"
    r"in\s+the|during|outside|without|with|for\s+your|left))|\bunavailable\b|\bnot running\b", re.I)
OFFERED = re.compile(r"\b(is|are|will be|being)\s+(offered|available)\b|\bhas\s+(open\s+)?sections?\b"
                     r"|\boffered\s+(next|in|this)\b|\bavailable\s+(next|in|this)\b", re.I)
ELIGIBLE = re.compile(r"\byou\s+(can|could|may|are able to)\s+(take|enroll|enrol|register|sign up)\b"
                      r"|\byou['’]?re\s+eligible\b|\byou\s+are\s+eligible\b|\byou\s+qualify\b"
                      r"|\byou\s+meet\s+(all\s+)?the\s+prerequisites?\b", re.I)
REQUIRE = re.compile(r"\b(prerequisites?|prereqs?|requires?|required|needs?|must|first|complete|completed|before)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE = re.compile(r";|,?\s+\b(?:but|however|whereas|while|although)\b", re.I)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s and s.strip()]


def _windows(text: str) -> list[str]:
    s = sentences(text)
    return s + [f"{a} {b}" for a, b in zip(s, s[1:])]


def _ids(text: str) -> set[str]:
    return {a + b for a, b in COURSE.findall(text or "")}


def _refs(text: str, titles: dict[str, str]) -> set[str]:
    low = (text or "").lower()
    return _ids(text) | {cid for title, cid in titles.items() if title in low}


def conflict(answer: str, a: str, b: str) -> bool:
    for w in _windows(answer):
        if a in w and b in w and CONFLICT.search(w) and not NO_CONFLICT.search(w):
            return True
    return False


def availability(answer: str, course: str, expected: str, titles: dict[str, str]) -> bool:
    says_not, says_yes = False, False
    for s in sentences(answer):
        for clause in _CLAUSE.split(s):
            if not clause or course not in _refs(clause, titles):
                continue
            if NOT_OFFERED.search(clause):
                says_not = True
            elif OFFERED.search(clause) or (SECTION.search(clause) and not NEG.search(clause)):
                says_yes = True
    return (says_not and not says_yes) if expected == "not_offered" else (says_yes and not says_not)


def ineligible(answer: str, course: str, missing: list[str], titles: dict[str, str]) -> bool:
    for w in _windows(answer):
        refs = _refs(w, titles)
        if course in refs and any(m in refs for m in missing) and REQUIRE.search(w):
            return True
    return False


def clarification(answer: str, candidates: list[str] | None = None, minimum: int = 0) -> bool:
    if "?" not in (answer or ""):
        return False
    low = answer.lower()
    return sum(1 for c in (candidates or []) if c.lower() in low) >= minimum


def sections_ok(answer: str, allowed: set[str], named_by_student: set[str]) -> tuple[bool, list[str]]:
    bad = []
    for s in sentences(answer):
        for sid in SECTION.findall(s):
            if sid in allowed:
                continue
            if sid in named_by_student and REJECT.search(s):
                continue
            bad.append(sid)
    return not bad, sorted(set(bad))


def recommends_option(answer: str, options: list[list[str]]) -> bool:
    return any(all(sid in answer for sid in option) for option in options)


def _claims(answer: str, titles: dict[str, str]) -> list[tuple[str, str, str]]:
    """(course, kind, clause) with kind in offered / not_offered / eligible."""
    out = []
    for s in sentences(answer):
        for clause in _CLAUSE.split(s):
            if not clause:
                continue
            refs = _refs(clause, titles)
            if not refs:
                continue
            if NOT_OFFERED.search(clause):
                out += [(c, "not_offered", clause) for c in refs]
            elif OFFERED.search(clause) and not NEG.search(clause):
                out += [(c, "offered", clause) for c in refs]
            if ELIGIBLE.search(clause) and not NEG.search(clause):
                out += [(c, "eligible", clause) for c in refs]
    return out


def false_claims(answer: str, truth: dict[str, dict], titles: dict[str, str]) -> list[dict]:
    """Statements that contradict the dataset. truth[course] = {"offered", "eligible"}."""
    found = []
    for course, kind, clause in _claims(answer, titles):
        t = truth.get(course)
        if t is None:
            continue  # course not in the catalog: nothing to compare with
        wrong = ((kind == "offered" and not t["offered"])
                 or (kind == "not_offered" and t["offered"])
                 or (kind == "eligible" and not t["eligible"]))
        if wrong:
            found.append({"course_id": course, "claim": kind, "text": clause.strip()[:200]})
    return found


def unsupported_claims(answer: str, trace: list[dict], titles: dict[str, str]) -> list[dict]:
    """Positive availability/eligibility statements with no plan_schedule support."""
    in_option, planned = set(), set()
    for t in trace:
        if t["tool"] != "plan_schedule" or not t["ok"]:
            continue
        planned |= {str(c).upper() for c in t["arguments"].get("course_ids", [])}
        for o in t["result"].get("options", []):
            in_option |= {s["course_id"] for s in o.get("sections", [])}
    found = []
    for course, kind, clause in _claims(answer, titles):
        backed = course in in_option if kind in ("offered", "eligible") else course in planned
        if not backed:
            found.append({"course_id": course, "claim": kind, "text": clause.strip()[:200]})
    return found


def truth_table(ds, student_id: str, term_id: str) -> dict[str, dict]:
    """Per catalog course: offered this term? may this student take it?"""
    student = ds.students.get(student_id)
    done = student.completed_courses if student else set()
    out = {}
    for cid, course in ds.courses.items():
        offered = any(s.course_id == cid and s.term_id == term_id for s in ds.sections.values())
        eligible = bool(student and student.active and offered and cid not in done
                        and all(p in done for p in course.prerequisites))
        out[cid] = {"offered": offered, "eligible": eligible}
    return out


def titles_of(ds) -> dict[str, str]:
    return {c.title.lower(): cid for cid, c in ds.courses.items() if c.title}
