"""Load the mock dataset from data/*.json into models.

Development/testing helper only. In the finished system the agent gets this
data from MCP tools, then builds the same models before validating.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import Course, Section, Student

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass
class Dataset:
    students: dict[str, Student]
    courses: dict[str, Course]
    sections: dict[str, Section]


def _read(data_dir: Path, name: str) -> list[dict]:
    with open(data_dir / name, encoding="utf-8") as f:
        return json.load(f)


def load_dataset(data_dir: Path | str = DEFAULT_DATA_DIR) -> Dataset:
    data_dir = Path(data_dir)
    history = _read(data_dir, "course_history.json")
    students = {
        s["student_id"]: Student.from_dict(
            s, [h for h in history if h["student_id"] == s["student_id"]]
        )
        for s in _read(data_dir, "students.json")
    }
    courses = {c["course_id"]: Course.from_dict(c) for c in _read(data_dir, "courses.json")}
    sections = {s["section_id"]: Section.from_dict(s) for s in _read(data_dir, "sections.json")}
    return Dataset(students=students, courses=courses, sections=sections)
