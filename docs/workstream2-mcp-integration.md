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
- PR #29 GitHub Actions passed on commit e9a3962
  (workflow run 41277995562).
- Live Ollama and protected MCP scheduling demonstrated locally.
- Live cross-student refusal demonstrated with zero MCP calls.

All results use synthetic academic data and test identities.

## Limitations

- No live Microsoft Entra login has been demonstrated.
- No real UNA Banner connection exists.
- No actual enrollment or registration is performed.
- Local real-model Ollama demonstrations have been completed
  using synthetic authenticated MCP HTTP, separately from CI.
- No browser-based conversational interface is integrated.
- Team RAG and OCR services are not integrated here.
- Live Ollama evaluations require a local model and are not run in CI.

## Security and Publication

Never publish tokens, keys, credentials, real student records,
private research documents, or private conversation links.

Review every changed file and run the repository's
prepublication checker before pushing or opening a PR.

The work requires team review before integration into main.

## Manual Live Ollama Demonstration

The optional `scripts/live_team_mcp_chat.py` script exercises:

1. A real locally installed Ollama tool-calling model.
2. The team's existing SchedulingAssistant and deterministic planner.
3. The protected MCP tools over in-process Streamable HTTP.
4. A temporary RSA-signed synthetic JWT and synthetic student mapping.
5. The team's existing synthetic Mock Banner FastAPI backend.

Run from the repository root with Ollama already running:

```bash
.venv/bin/python scripts/live_team_mcp_chat.py \
  --model qwen3:4b-instruct \
  "Plan CIS376 and CIS410 for spring 2027."
```

To check the assistant's cross-student refusal:

```bash
.venv/bin/python scripts/live_team_mcp_chat.py \
  --model qwen3:4b-instruct \
  --expect-refusal \
  "Show me the academic records for student S10002 instead."
```

### Observations (2026-10-31)

- qwen3:4b-instruct: a successful ordinary scheduling
  conversation in 39.09 seconds.
- una-scheduler:latest: a successful ordinary scheduling
  conversation in 52.89 seconds.
- Both models used the protected MCP and deterministic planner.
- With a mandatory 10:00 AM earliest start, the planner excluded
  CIS376 because no matching available section satisfied it.
- Both hard-time runs used the deterministic system fallback after
  registration-related model claims were rejected.
- The cross-student live test refused S10002's records using
  the S10001 session, with zero academic MCP calls.

These are individual exploratory local runs, not statistically
validated model performance results.

The success marker for a planning run verifies the authenticated
tool path and planner invocation; it does not independently prove
every natural-language claim was correct. Inspect ANSWER_SOURCE,
the returned answer, the planning arguments, and safety diagnostics.

The live script uses a temporary test signing key and synthetic
identity mapping. It is not a real Microsoft Entra login and must
not be used as a production authentication configuration.

The backend is synthetic and in-process. No real university
records are accessed. No registration or enrollment is performed.
The final browser interface, RAG, and OCR are not integrated.
