"""Data models for deterministic schedule validation.

Field names match docs/mock-data-model.md and the JSON files in data/.
The validators only depend on these models, not on where the data came
from, so the same code works with the JSON files today and with MCP tool
results later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


def parse_time(value: str) -> int:
    """Convert "HH:MM" (24-hour) to minutes after midnight."""
    hours, minutes = value.split(":")
    h, m = int(hours), int(minutes)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"invalid time: {value!r}")
    return h * 60 + m


@dataclass(frozen=True)
class Meeting:
    days: tuple[str, ...]
    start: int  # minutes after midnight
    end: int
    location: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Meeting":
        days = tuple(d["days"])
        unknown = set(days) - VALID_DAYS
        if unknown:
            raise ValueError(f"invalid day values: {sorted(unknown)}")
        start, end = parse_time(d["start_time"]), parse_time(d["end_time"])
        if end <= start:
            raise ValueError(f"meeting ends before it starts: {d}")
        return cls(days=days, start=start, end=end, location=d.get("location", ""))

    def overlaps(self, other: "Meeting") -> bool:
        shares_day = bool(set(self.days) & set(other.days))
        # Back-to-back meetings (one ends 10:45, next starts 10:45) do not overlap.
        return shares_day and self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Course:
    course_id: str
    title: str
    credit_hours: int
    prerequisites: tuple[str, ...] = ()
    corequisites: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "Course":
        return cls(
            course_id=d["course_id"],
            title=d.get("title", ""),
            credit_hours=int(d["credit_hours"]),
            prerequisites=tuple(d.get("prerequisites", [])),
            corequisites=tuple(d.get("corequisites", [])),
        )


@dataclass(frozen=True)
class Section:
    section_id: str
    course_id: str
    term_id: str
    section_number: str
    modality: str
    capacity: int
    enrolled_count: int
    meetings: tuple[Meeting, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(
            section_id=d["section_id"],
            course_id=d["course_id"],
            term_id=d["term_id"],
            section_number=d.get("section_number", ""),
            modality=d.get("modality", ""),
            capacity=int(d["capacity"]),
            enrolled_count=int(d["enrolled_count"]),
            meetings=tuple(Meeting.from_dict(m) for m in d.get("meetings", [])),
        )

    @property
    def seats_available(self) -> int:
        return self.capacity - self.enrolled_count


@dataclass(frozen=True)
class CourseRecord:
    course_id: str
    term_id: str
    grade: str
    status: str  # completed | in_progress | failed | withdrawn

    @classmethod
    def from_dict(cls, d: dict) -> "CourseRecord":
        return cls(
            course_id=d["course_id"],
            term_id=d["term_id"],
            grade=d.get("grade", ""),
            status=d["status"],
        )


@dataclass(frozen=True)
class Student:
    student_id: str
    program: str
    max_credit_hours: int
    active: bool
    history: tuple[CourseRecord, ...] = field(default=())

    @classmethod
    def from_dict(cls, d: dict, history: list[dict] | None = None) -> "Student":
        return cls(
            student_id=d["student_id"],
            program=d.get("program", ""),
            max_credit_hours=int(d["max_credit_hours"]),
            active=bool(d["active"]),
            history=tuple(CourseRecord.from_dict(h) for h in (history or [])),
        )

    @property
    def completed_courses(self) -> set[str]:
        # WORKING ASSUMPTION: only status "completed" satisfies a prerequisite.
        # Minimum grades are not enforced yet (see docs/mock-data-model.md).
        return {r.course_id for r in self.history if r.status == "completed"}
