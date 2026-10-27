# UNA MCP Scheduling Research Project

## Mock Banner API

This repository contains the synthetic academic-data backend used by the UNA MCP AI Scheduling Research Project.

The Mock Banner API provides a controlled development and testing environment without connecting to the production UNA Banner system or using real student records.

## Purpose

The API exposes synthetic academic information required by the scheduling research prototype, including:

- Students
- Courses
- Course history
- Academic terms
- Course sections
- Enrollments

The Mock Banner API is designed to provide a stable academic-data interface for the MCP server while allowing the backend implementation to be replaced by a future UNA-approved Banner integration.

## Technology

- Python
- FastAPI
- Uvicorn
- Pytest
- JSON synthetic datasets

## Project Structure

```text
una-mcp-scheduler/
├── app/
│   ├── __init__.py
│   └── main.py
├── data/
│   ├── students.json
│   ├── courses.json
│   ├── course_history.json
│   ├── terms.json
│   ├── sections.json
│   └── enrollments.json
├── docs/
├── tests/
│   └── test_api.py
├── requirements.txt
├── requirements-dev.txt
└── README.md