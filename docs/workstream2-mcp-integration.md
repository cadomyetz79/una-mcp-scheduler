# Workstream 2 — Protected MCP Integration

## Status

CONFIRMED: The synthetic WS3 → WS2 → WS1 integration
has passed local tests using the team's own Python environment.

This is a research prototype, not a production university service.

## Architecture

- WS3: Team AI agent, BannerTools client, and deterministic planner.
- WS2: Authenticated MCP server, student-access policy, and tool adapter.
- WS1: Team Mock Banner API with synthetic academic records.

The internal WS2 adapter uses HTTPX ASGITransport to call
the existing team FastAPI application in-process.

No team WS1 datasets or WS3 implementation files were replaced.

## MCP Tool Contract

The protected server exposes six read-only tools:

1. get_student_record(student_id)
2. get_course_history(student_id)
3. get_course(course_id)
4. search_courses(query, subject)
5. get_course_sections(course_id, term_id)
6. get_student_enrollments(student_id, term_id)

Student-specific tools check the authenticated student's
identity before accessing the backend.

MCP list results use structured JSON compatible with the
team's existing BannerTools client.

## Development Setup

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mcp-dev.txt
.venv/bin/python -m pytest -q tests/
cd ai-agent
../.venv/bin/python -m pytest -q
```

## Local Service

From the repository root:

```bash
.venv/bin/python -m src.mcp_server.team_service
```

The MCP service binds to 127.0.0.1:8002, path /mcp.

Without configured Entra application identifiers, its token
verifier rejects all bearer tokens.

The default student identity mapping is empty. Supplying
Entra configuration alone does not enable student access.

Do not expose this prototype as a public or production service.

## Verified Local Results

- WS1 + WS2 root suite: 53 passed.
- WS3 agent suite: 874 passed, 1 skipped.
- Signed synthetic JWT MCP HTTP test: passed.
- Student-specific cross-access rejection: tested.
- Independent team Python environment: verified.
- Loopback-only service startup and HTTP 401: verified.

All results use synthetic academic data and test identities.

## Limitations

- No live Microsoft Entra login has been demonstrated.
- No real UNA Banner connection exists.
- No actual enrollment or registration is performed.
- The live conversational AI model and browser UI are not
  part of this combined integration test.
- Team RAG and OCR services are not integrated here.
- GitHub Actions results remain unverified until CI runs.

## Security and Publication

Never publish tokens, keys, credentials, real student records,
private research documents, or private conversation links.

Review every changed file and run the repository's
prepublication checker before pushing or opening a PR.

The work requires team review before integration into main.
