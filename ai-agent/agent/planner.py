"""Deterministic schedule generation on top of the MCP tools.

Given a student, a term and the courses they want, the planner:
  1. fetches everything it needs through MCP (BannerTools),
  2. drops courses the student cannot take (prerequisites, already completed,
     no sections this term) and sections that are full or break a stated
     preference,
  3. tries every combination of the remaining sections, and
  4. keeps only combinations that validate_schedule() accepts.

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


@dataclass
class Preferences:
    earliest_start: str | None = None  # "HH:MM"; no meeting may start before this
    latest_end: str | None = None  # "HH:MM"; no meeting may end after this
    avoid_days: tuple[str, ...] = ()  # e.g. ("FRI",)

    def allows(self, section: Section) -> bool:
        start = parse_time(self.earliest_start) if self.earliest_start else None
        end = parse_time(self.latest_end) if self.latest_end else None
        for m in section.meetings:
            if start is not None and m.start < start:
                return False
            if end is not None and m.end > end:
                return False
            if set(m.days) & set(self.avoid_days):
                return False
        return True


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
) -> PlanResult:
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

    if not candidates:
        return result

    rejections: Counter[str] = Counter()
    combos = product(*candidates.values())
    for combo in islice(combos, MAX_COMBINATIONS):
        result.combinations_checked += 1
        ids = [s.section_id for s in combo]
        check = validate_schedule(student, ids, term_id, all_sections, courses)
        if check.valid:
            result.options.append(
                {
                    "section_ids": ids,
                    "total_credit_hours": check.total_credit_hours,
                    "sections": [_describe(s) for s in combo],
                }
            )
            if len(result.options) >= max_options:
                break
        else:
            rejections.update(i.code for i in check.issues)

    result.rejection_counts = dict(rejections)
    return result
