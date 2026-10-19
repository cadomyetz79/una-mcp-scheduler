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

from .banner_tools import BannerTools, ToolCallError

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
) -> PlanResult:
    """requested_sections: section IDs the student named. They are checked as
    one combination with validate_schedule (time conflicts, capacity,
    prerequisites, ...), and a section that is not a section of the requested
    courses in this term is reported as not found. This answers "can I take
    SEC5001 with SEC5301?" deterministically instead of leaving the model to
    infer it from which options are missing."""
    prefs = preferences or Preferences()
    requested = list(dict.fromkeys(course_ids))  # de-duplicate, keep order
    result = PlanResult(student_id, term_id, requested)

    student = await tools.student(student_id)

    courses = {}
    for cid in requested:
        try:
            courses[cid] = await tools.course(cid)
        except ToolCallError:
            result.excluded.append(Excluded(cid, "UNKNOWN_COURSE", f"{cid} does not exist."))

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
            student, list(dict.fromkeys(requested_sections)), term_id, all_sections, courses)

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
            valid.append(
                {
                    "section_ids": ids,
                    "total_credit_hours": check.total_credit_hours,
                    "meets_all_preferences": not misses,
                    "preference_violations": misses,
                    "sections": [_describe(s) for s in combo],
                }
            )
        else:
            rejections.update(i.code for i in check.issues)

    # Rank: fewest missed preferences, then least total minutes missed.
    # sorted() is stable, so ties keep enumeration order (deterministic).
    valid.sort(
        key=lambda o: (
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


def check_requested_sections(student, section_ids: list[str], term_id: str,
                             all_sections: dict[str, Section], courses: dict) -> dict:
    """Validate the student's named sections as one combination."""
    found = [sid for sid in section_ids if sid in all_sections]
    not_found = [sid for sid in section_ids if sid not in all_sections]
    issues = []
    if found:
        check = validate_schedule(student, found, term_id, all_sections, courses)
        issues = [{"code": i.code, "message": i.message, "section_ids": list(i.section_ids)}
                  for i in check.issues]
    return {
        "section_ids": section_ids,
        "sections": [_describe(all_sections[sid]) for sid in found],
        "not_found": not_found,
        "not_found_reason": (f"not a {term_id} section of the planned course(s) "
                             f"{', '.join(sorted(courses)) or '(none)'}") if not_found else None,
        "valid_together": bool(found) and not not_found and not issues,
        "issues": issues,
        "in_returned_options": False,
    }
