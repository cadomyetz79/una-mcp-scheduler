import json
from pathlib import Path

from fastapi import FastAPI


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