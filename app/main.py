import json
from pathlib import Path

from fastapi import FastAPI, HTTPException


app = FastAPI(
    title="UNA Mock Banner API",
    description="Synthetic academic data API for the UNA MCP Scheduling Research Project",
    version="0.1.0"
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_json(filename: str):
    file_path = DATA_DIR / filename

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "UNA Mock Banner API"
    }


@app.get("/students")
def get_students():
    return load_json("students.json")

@app.get("/students/{student_id}")
def get_student(student_id: str):
    students = load_json("students.json")

    for student in students:
        if student["student_id"] == student_id:
            return student

    raise HTTPException(
        status_code=404,
        detail="Student not found"
    )

@app.get("/courses")
def get_courses():
    return load_json("courses.json")


@app.get("/courses/{course_id}")
def get_course(course_id: str):
    courses = load_json("courses.json")

    for course in courses:
        if course["course_id"] == course_id:
            return course

    raise HTTPException(
        status_code=404,
        detail="Course not found"
    )

@app.get("/sections")
def get_sections(
    course_id: str | None = None,
    term_id: str | None = None
):
    sections = load_json("sections.json")

    if course_id:
        sections = [
            section
            for section in sections
            if section["course_id"] == course_id
        ]

    if term_id:
        sections = [
            section
            for section in sections
            if section["term_id"] == term_id
        ]

    return sections

@app.get("/sections/{section_id}")
def get_section(section_id: str):
    sections = load_json("sections.json")

    for section in sections:
        if section["section_id"] == section_id:
            return section

    raise HTTPException(
        status_code=404,
        detail="Section not found"
    )