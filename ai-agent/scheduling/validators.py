"""Deterministic academic-rule checks for a proposed schedule.

Design rule: the LLM never decides whether a schedule is valid. It proposes
a list of section IDs; validate_schedule() decides, and returns machine-
readable issues the agent can explain to the student or use to retry.

Every check returns a list of Issue objects. An empty list means the check
passed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations

from .models import Course, Section, Student


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    section_ids: tuple[str, ...] = ()
    course_ids: tuple[str, ...] = ()


@dataclass
class ValidationResult:
    valid: bool
    total_credit_hours: int
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-friendly form, for returning to the agent / LLM."""
        return {
            "valid": self.valid,
            "total_credit_hours": self.total_credit_hours,
            "issues": [asdict(i) for i in self.issues],
        }


# ---------------------------------------------------------------- checks


def check_student_active(student: Student) -> list[Issue]:
    if student.active:
        return []
    return [Issue("STUDENT_INACTIVE", f"Student {student.student_id} is not active.")]


def check_single_term(sections: list[Section], term_id: str) -> list[Issue]:
    return [
        Issue(
            "WRONG_TERM",
            f"{s.section_id} ({s.course_id}) is in term {s.term_id}, not {term_id}.",
            section_ids=(s.section_id,),
            course_ids=(s.course_id,),
        )
        for s in sections
        if s.term_id != term_id
    ]


def check_duplicate_courses(sections: list[Section]) -> list[Issue]:
    seen: dict[str, str] = {}
    issues = []
    for s in sections:
        if s.course_id in seen:
            issues.append(
                Issue(
                    "DUPLICATE_COURSE",
                    f"{s.course_id} appears twice ({seen[s.course_id]} and {s.section_id}).",
                    section_ids=(seen[s.course_id], s.section_id),
                    course_ids=(s.course_id,),
                )
            )
        else:
            seen[s.course_id] = s.section_id
    return issues


def check_already_completed(student: Student, sections: list[Section]) -> list[Issue]:
    done = student.completed_courses
    return [
        Issue(
            "ALREADY_COMPLETED",
            f"Student already completed {s.course_id}.",
            section_ids=(s.section_id,),
            course_ids=(s.course_id,),
        )
        for s in sections
        if s.course_id in done
    ]


def check_prerequisites(
    student: Student, sections: list[Section], courses: dict[str, Course]
) -> list[Issue]:
    """All listed prerequisites must be completed (AND rule) before the term."""
    done = student.completed_courses
    issues = []
    for s in sections:
        missing = [p for p in courses[s.course_id].prerequisites if p not in done]
        if missing:
            issues.append(
                Issue(
                    "MISSING_PREREQUISITE",
                    f"{s.course_id} requires {', '.join(missing)}.",
                    section_ids=(s.section_id,),
                    course_ids=(s.course_id, *missing),
                )
            )
    return issues


def check_corequisites(
    student: Student, sections: list[Section], courses: dict[str, Course]
) -> list[Issue]:
    """A corequisite is satisfied if already completed or in the same schedule."""
    available = student.completed_courses | {s.course_id for s in sections}
    issues = []
    for s in sections:
        missing = [c for c in courses[s.course_id].corequisites if c not in available]
        if missing:
            issues.append(
                Issue(
                    "MISSING_COREQUISITE",
                    f"{s.course_id} must be taken with {', '.join(missing)}.",
                    section_ids=(s.section_id,),
                    course_ids=(s.course_id, *missing),
                )
            )
    return issues


def check_capacity(sections: list[Section]) -> list[Issue]:
    return [
        Issue(
            "SECTION_FULL",
            f"{s.section_id} ({s.course_id}) is full ({s.enrolled_count}/{s.capacity}).",
            section_ids=(s.section_id,),
            course_ids=(s.course_id,),
        )
        for s in sections
        if s.seats_available <= 0
    ]


def check_time_conflicts(sections: list[Section]) -> list[Issue]:
    """Sections with no meetings (e.g. online async) never conflict."""
    issues = []
    for a, b in combinations(sections, 2):
        if any(ma.overlaps(mb) for ma in a.meetings for mb in b.meetings):
            issues.append(
                Issue(
                    "TIME_CONFLICT",
                    f"{a.section_id} ({a.course_id}) overlaps {b.section_id} ({b.course_id}).",
                    section_ids=(a.section_id, b.section_id),
                    course_ids=(a.course_id, b.course_id),
                )
            )
    return issues


def total_credits(sections: list[Section], courses: dict[str, Course]) -> int:
    return sum(courses[s.course_id].credit_hours for s in sections)


def check_credit_limit(
    student: Student, sections: list[Section], courses: dict[str, Course]
) -> list[Issue]:
    total = total_credits(sections, courses)
    if total <= student.max_credit_hours:
        return []
    return [
        Issue(
            "CREDIT_LIMIT_EXCEEDED",
            f"Schedule has {total} credit hours; limit is {student.max_credit_hours}.",
        )
    ]


# ---------------------------------------------------------------- entry point


def validate_schedule(
    student: Student,
    section_ids: list[str],
    term_id: str,
    sections_by_id: dict[str, Section],
    courses: dict[str, Course],
) -> ValidationResult:
    """Validate a proposed schedule (a list of section IDs) for one term."""
    issues: list[Issue] = []

    unknown = [sid for sid in section_ids if sid not in sections_by_id]
    for sid in unknown:
        issues.append(Issue("UNKNOWN_SECTION", f"Section {sid} does not exist.", (sid,)))
    sections = [sections_by_id[sid] for sid in section_ids if sid in sections_by_id]

    unknown_courses = {s.course_id for s in sections if s.course_id not in courses}
    for cid in sorted(unknown_courses):
        issues.append(Issue("UNKNOWN_COURSE", f"Course {cid} does not exist.", (), (cid,)))
    sections = [s for s in sections if s.course_id in courses]

    issues += check_student_active(student)
    issues += check_single_term(sections, term_id)
    issues += check_duplicate_courses(sections)
    issues += check_already_completed(student, sections)
    issues += check_prerequisites(student, sections, courses)
    issues += check_corequisites(student, sections, courses)
    issues += check_capacity(sections)
    issues += check_time_conflicts(sections)
    issues += check_credit_limit(student, sections, courses)

    return ValidationResult(
        valid=not issues,
        total_credit_hours=total_credits(sections, courses),
        issues=issues,
    )
