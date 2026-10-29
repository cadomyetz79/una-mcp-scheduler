"""Deterministic schedule generation on top of the MCP tools.

Given a student, a term and the courses they want, the planner:
  1. fetches everything it needs through MCP (BannerTools),
  2. drops courses the student cannot take (prerequisites, already completed,
     no sections this term) and sections that are full or break a REQUIRED
     preference,
  3. tries every combination of the remaining sections,
  4. keeps only combinations that validate_schedule() accepts, and
  5. ranks the valid ones: fewer violated soft preferences first.

Hard constraints (validate_schedule, full sections, required preferences)
decide validity. Soft preferences never make a schedule invalid; they only
order the valid ones and are reported on each option.

No LLM is involved here. Later the LLM's job is to turn a student's words
("no classes before 10") into these arguments, and to explain the result.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import islice, product

from scheduling.models import Section, parse_time
from scheduling.validators import (
    check_already_completed,
    check_prerequisites,
    validate_schedule,
)

from .banner_tools import BackendError, BannerTools, ToolCallError

MAX_COMBINATIONS = 10_000  # safety cap on brute-force enumeration


PREFERENCE_NAMES = ("earliest_start", "latest_end", "avoid_days")


@dataclass
class Preferences:
    earliest_start: str | None = None  # "HH:MM"; meetings should not start before this
    latest_end: str | None = None  # "HH:MM"; meetings should not end after this
    avoid_days: tuple[str, ...] = ()  # e.g. ("FRI",)
    # Which of the preferences above are MANDATORY (hard). Anything not listed
    # is soft: it ranks valid schedules but never invalidates one.
    # Default = all mandatory, which is the behaviour before ranking existed.
    required: tuple[str, ...] = PREFERENCE_NAMES

    def violations(self, section: Section) -> list[dict]:
        """Every way this section misses a stated preference (hard or soft)."""
        start = parse_time(self.earliest_start) if self.earliest_start else None
        end = parse_time(self.latest_end) if self.latest_end else None
        found: list[dict] = []
        for m in section.meetings:
            if start is not None and m.start < start:
                found.append(self._violation(section, "earliest_start", start_gap=start - m.start))
            if end is not None and m.end > end:
                found.append(self._violation(section, "latest_end", end_gap=m.end - end))
            hit = sorted(set(m.days) & set(self.avoid_days))
            if hit:
                found.append(self._violation(section, "avoid_days", days=hit))
        return found

    @staticmethod
    def _violation(section: Section, preference: str, **info) -> dict:
        excess = info.get("start_gap", info.get("end_gap", 0))
        detail = {
            "earliest_start": f"starts {excess} min before the requested time",
            "latest_end": f"ends {excess} min after the requested time",
            "avoid_days": f"meets on {', '.join(info.get('days', []))}",
        }[preference]
        return {
            "section_id": section.section_id,
            "preference": preference,
            "detail": detail,
            "excess_minutes": excess,
        }

    def allows(self, section: Section) -> bool:
        """False if the section breaks a REQUIRED preference."""
        return not any(v["preference"] in self.required for v in self.violations(section))


@dataclass
class Excluded:
    course_id: str
    code: str
    reason: str


@dataclass
class PlanResult:
    student_id: str
    term_id: str
    requested: list[str]
    options: list[dict] = field(default_factory=list)
    excluded: list[Excluded] = field(default_factory=list)
    combinations_checked: int = 0
    rejection_counts: dict[str, int] = field(default_factory=dict)
    # Honest reporting of limits: how many valid schedules exist vs. returned,
    # and whether the brute-force search was cut off by MAX_COMBINATIONS.
    total_valid_options: int = 0
    options_truncated: bool = False
    search_capped: bool = False
    # Specific sections the student named, checked as one combination by
    # validate_schedule (None when no sections were named).
    requested_sections: dict | None = None
    # Current registrations this term (see plan_schedules): True = checked,
    # False = the backend could not say (the answer must then say so),
    # None = not attempted.
    current_registrations_checked: bool | None = None
    current_registrations: list[dict] = field(default_factory=list)
    already_registered: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["excluded"] = [asdict(e) for e in self.excluded]
        return d


def _describe(section: Section) -> dict:
    return {
        "section_id": section.section_id,
        "course_id": section.course_id,
        "modality": section.modality,
        "seats_available": section.seats_available,
        "meetings": [
            {
                "days": list(m.days),
                "start": f"{m.start // 60:02d}:{m.start % 60:02d}",
                "end": f"{m.end // 60:02d}:{m.end % 60:02d}",
                "location": m.location,
            }
            for m in section.meetings
        ],
    }


async def plan_schedules(
    tools: BannerTools,
    student_id: str,
    term_id: str,
    course_ids: list[str],
    preferences: Preferences | None = None,
    max_options: int = 5,
    requested_sections: list[str] | None = None,
    check_current_registrations: bool = True,
) -> PlanResult:
    """requested_sections: section IDs the student named. They are checked as
    one combination with validate_schedule (time conflicts, capacity,
    prerequisites, ...), and a section that is not a section of the requested
    courses in this term is reported as not found. This answers "can I take
    SEC5001 with SEC5301?" deterministically instead of leaving the model to
    infer it from which options are missing.

    Current registrations (integration audit 2026-10-19): if the backend can
    list the sections the student is already registered in this term, every
    option is checked against them: a requested course the student is
    already registered for, a time overlap with a current class, and the
    credit limit including current classes. Whether such options should be
    removed is an open team decision (it depends on what an enrollment means
    in Workstream 1's data), so they are NOT removed: they are flagged
    (`current_registration`, `compatible_with_current_registration`,
    `registration_fit`) and ranked after compatible options, and the
    assistant states the problem. An option that contains a section the
    student is already registered in simply keeps it (no change needed);
    another section of a registered course is a section switch, which is a
    change. Every option gets `registration_fit`:
      "fits_current_registration"     checked, no change needed
      "requires_registration_change"  switch, overlap or credit limit
      "not_confirmed"                 checked, but credits could not be read
      "not_checked"                   registrations could not be listed
    If the backend cannot list registrations, `current_registrations_checked`
    is False and the assistant says so; it is never silently ignored.

    Course lookups: only a "not found" answer makes a course UNKNOWN_COURSE.
    Any other backend failure propagates (BackendError), so an outage is never
    reported as "this course does not exist"."""
    prefs = preferences or Preferences()
    requested = list(dict.fromkeys(course_ids))  # de-duplicate, keep order
    result = PlanResult(student_id, term_id, requested)

    student = await tools.student(student_id)

    current: list[Section] = []
    get_current = getattr(tools, "enrollments", None)
    if check_current_registrations and get_current is not None:
        listed = await get_current(student_id, term_id)
        result.current_registrations_checked = listed is not None
        current = [s for s in (listed or []) if s.term_id == term_id]
        result.current_registrations = [_describe(s) for s in current]

    courses = {}
    for cid in requested:
        try:
            courses[cid] = await tools.course(cid)
        except ToolCallError as e:
            if e.code != "not_found":
                raise
            result.excluded.append(Excluded(cid, "UNKNOWN_COURSE", f"{cid} does not exist."))

    # Credit hours of current registrations (None if a course cannot be read).
    current_credits: int | None = 0
    for cid in dict.fromkeys(s.course_id for s in current):
        if cid in courses:
            current_credits += courses[cid].credit_hours
            continue
        try:
            current_credits += (await tools.course(cid)).credit_hours
        except BackendError:
            current_credits = None
            break
    registered_courses = {s.course_id: s for s in current}
    for cid in requested:
        if cid in registered_courses:
            result.already_registered.append(
                {"course_id": cid, "current_section": _describe(registered_courses[cid])})

    candidates: dict[str, list[Section]] = {}
    all_sections: dict[str, Section] = {}
    for cid, course in courses.items():
        sections = await tools.sections(cid, term_id)
        all_sections.update({s.section_id: s for s in sections})
        if not sections:
            result.excluded.append(
                Excluded(cid, "NO_SECTIONS_IN_TERM", f"{cid} is not offered in {term_id}.")
            )
            continue

        # Course-level rules: same validator functions, applied to one section.
        course_issues = check_already_completed(student, sections[:1]) + check_prerequisites(
            student, sections[:1], courses
        )
        if course_issues:
            result.excluded.extend(Excluded(cid, i.code, i.message) for i in course_issues)
            continue

        open_sections = [s for s in sections if s.seats_available > 0]
        if not open_sections:
            result.excluded.append(Excluded(cid, "ALL_SECTIONS_FULL", f"Every {cid} section is full."))
            continue

        preferred = [s for s in open_sections if prefs.allows(s)]
        if not preferred:
            result.excluded.append(
                Excluded(cid, "NO_SECTION_MATCHES_PREFERENCES",
                         f"No open {cid} section fits the requested times/days.")
            )
            continue
        candidates[cid] = preferred

    if requested_sections:
        result.requested_sections = check_requested_sections(
            student, list(dict.fromkeys(requested_sections)), term_id, all_sections, courses, requested,
            current if result.current_registrations_checked else None, current_credits,
            checked=result.current_registrations_checked, preferences=prefs)

    if not candidates:
        return result

    rejections: Counter[str] = Counter()
    space = 1
    for sections in candidates.values():
        space *= len(sections)
    result.search_capped = space > MAX_COMBINATIONS

    valid: list[dict] = []
    for combo in islice(product(*candidates.values()), MAX_COMBINATIONS):
        result.combinations_checked += 1
        ids = [s.section_id for s in combo]
        check = validate_schedule(student, ids, term_id, all_sections, courses)
        if check.valid:
            misses = [v for sec in combo for v in prefs.violations(sec)]
            option = {
                "section_ids": ids,
                "total_credit_hours": check.total_credit_hours,
                "meets_all_preferences": not misses,
                "preference_violations": misses,
                "sections": [_describe(s) for s in combo],
            }
            if result.current_registrations_checked:
                option.update(_against_current(combo, current, courses, current_credits,
                                               student.max_credit_hours))
            else:
                option["registration_fit"] = "not_checked"
            valid.append(option)
        else:
            rejections.update(i.code for i in check.issues)

    # Rank: compatible with current registrations first, then fewest missed
    # preferences, then least total minutes missed.
    # sorted() is stable, so ties keep enumeration order (deterministic).
    valid.sort(
        key=lambda o: (
            o.get("compatible_with_current_registration", True) is not True,
            len(o["preference_violations"]),
            sum(v["excess_minutes"] for v in o["preference_violations"]),
        )
    )
    for rank, option in enumerate(valid, start=1):
        option["rank"] = rank
    result.total_valid_options = len(valid)
    result.options_truncated = len(valid) > max_options
    result.options = valid[:max_options]
    result.rejection_counts = dict(rejections)
    if result.requested_sections is not None:
        wanted = set(result.requested_sections["section_ids"])
        result.requested_sections["in_returned_options"] = any(
            wanted <= set(o["section_ids"]) for o in result.options)
    return result


def _overlaps(a: Section, b: Section) -> bool:
    return any(ma.overlaps(mb) for ma in a.meetings for mb in b.meetings)


def _against_current(combo, current: list[Section], courses: dict, current_credits: int | None,
                     limit: int) -> dict:
    """How one option fits with the sections the student is already registered in.

    keeps_current_sections  sections of the option the student is already in (no change)
    switches_section_of     courses the student is registered in, but in another section
    conflicts               new sections that overlap a current class of another course
    credit_hours_with_current / exceeds_credit_limit  (None if a current course could not be read)
    """
    current_ids = {s.section_id for s in current}
    current_courses = {s.course_id for s in current}
    kept = sorted(s.section_id for s in combo if s.section_id in current_ids)
    switches = sorted({s.course_id for s in combo if s.course_id in current_courses and s.section_id not in current_ids})
    conflicts = [
        {"section_id": a.section_id, "course_id": a.course_id,
         "current_section_id": b.section_id, "current_course_id": b.course_id}
        for a in combo if a.section_id not in current_ids
        for b in current if b.course_id != a.course_id and _overlaps(a, b)
    ]
    # Credits if the option is added to current registrations (a course already
    # registered is counted once). None if a current course could not be read.
    with_current = None
    if current_credits is not None:
        with_current = current_credits + sum(courses[s.course_id].credit_hours
                                             for s in combo if s.course_id not in current_courses)
    exceeds = None if with_current is None else with_current > limit
    if switches or conflicts or exceeds:
        compatible, fit = False, "requires_registration_change"
    elif exceeds is None:
        compatible, fit = None, "not_confirmed"
    else:
        compatible, fit = True, "fits_current_registration"
    return {
        "current_registration": {
            "keeps_current_sections": kept,
            "switches_section_of": switches,
            "conflicts": conflicts,
            "credit_hours_with_current": with_current,
            "credit_limit": limit,
            "exceeds_credit_limit": exceeds,
        },
        "compatible_with_current_registration": compatible,
        "registration_fit": fit,
    }


def _required_preference_issues(sections: list[Section], prefs: Preferences | None) -> list[dict]:
    """One issue per named section and broken REQUIRED preference."""
    if prefs is None:
        return []
    limit = {
        "earliest_start": f"starts before {prefs.earliest_start}, the earliest time you said you can start",
        "latest_end": f"ends after {prefs.latest_end}, the time you said you need to be done by",
    }
    issues = []
    for s in sections:
        seen: set[str] = set()
        for v in prefs.violations(s):
            pref = v["preference"]
            if pref not in prefs.required or pref in seen:
                continue
            seen.add(pref)
            days = [d for d in prefs.avoid_days if any(d in m.days for m in s.meetings)]
            what = limit.get(pref) or f"meets on {', '.join(days)}, a day you said you need to keep free"
            issues.append({"code": "REQUIRED_PREFERENCE_VIOLATION", "preference": pref,
                           "message": f"{s.section_id} ({s.course_id}) {what}.", "section_ids": [s.section_id]})
    return issues


def check_requested_sections(student, section_ids: list[str], term_id: str,
                             all_sections: dict[str, Section], courses: dict,
                             requested: list[str] | None = None,
                             current: list[Section] | None = None,
                             current_credits: int | None = None,
                             checked: bool | None = None,
                             preferences: Preferences | None = None) -> dict:
    """Validate the student's named sections as one combination.

    A named section that breaks a REQUIRED preference is an issue too
    (REQUIRED_PREFERENCE_VIOLATION), so it is never valid_together: the same
    mandatory limits that filter the options apply to sections the student
    names (audit 2026-10-29, H1). Before, "I can't do Mondays. Can I take
    SEC1001 with SEC2002?" was confirmed although SEC1001 meets on Monday.

    not_found_reason completes the sentence "<section> ...": a section is
    looked up only among the sections of the planned courses, so it is either
    not a section of them this term, or could not be checked at all because
    no planned course is in the catalog."""
    found = [sid for sid in section_ids if sid in all_sections]
    not_found = [sid for sid in section_ids if sid not in all_sections]
    issues = []
    if found:
        check = validate_schedule(student, found, term_id, all_sections, courses)
        issues = [{"code": i.code, "message": i.message, "section_ids": list(i.section_ids)}
                  for i in check.issues]
        issues += _required_preference_issues([all_sections[sid] for sid in found], preferences)
    # Fit with current registrations is reported apart from academic validity
    # (valid_together), so a valid combination that needs a registration change
    # is never presented as one the student can simply add.
    registration_issues = []
    current_ids = {s.section_id for s in current or []}
    current_courses = {s.course_id for s in current or []}
    for sid in found:
        a = all_sections[sid]
        if a.course_id in current_courses and sid not in current_ids:
            registration_issues.append({
                "code": "SWITCHES_CURRENT_SECTION", "section_ids": [sid],
                "message": f"{sid} is another section of {a.course_id}, which you're already registered for; "
                           f"taking it means changing your current {a.course_id} section."})
        for b in current or []:
            if b.section_id != sid and b.course_id != a.course_id and _overlaps(a, b):
                registration_issues.append({
                    "code": "CONFLICTS_WITH_CURRENT_REGISTRATION", "section_ids": [sid],
                    "message": f"{sid} ({a.course_id}) overlaps your current {b.course_id} class."})
    if found and current is not None and current_credits is not None:
        added = sum(courses[c].credit_hours for c in {all_sections[sid].course_id for sid in found}
                    if c in courses and c not in current_courses)
        if current_credits + added > student.max_credit_hours:
            registration_issues.append({
                "code": "CREDIT_LIMIT_WITH_CURRENT", "section_ids": list(found),
                "message": f"Together with your current classes, {', '.join(found)} would bring you to "
                           f"{current_credits + added} credit hours, over your limit of {student.max_credit_hours}."})
    if checked is not True:
        fits = None
    elif current_credits is None and not registration_issues:
        fits = None
    else:
        fits = bool(found) and not registration_issues
    return {
        "section_ids": section_ids,
        "sections": [_describe(all_sections[sid]) for sid in found],
        "not_found": not_found,
        "not_found_reason": None if not not_found else (
            f"is not a {term_id} section of the planned course(s) {', '.join(sorted(courses))}" if courses
            else f"could not be checked because {', '.join(requested or []) or 'the planned course'} "
                 "is not in the course catalog"),
        "valid_together": bool(found) and not not_found and not issues,
        "issues": issues,
        # True: checked and no change to current registrations needed; False: a change
        # is needed (registration_issues); None: registrations not checked / not confirmed
        "fits_current_registration": fits,
        "registration_issues": registration_issues,
        "in_returned_options": False,
    }
