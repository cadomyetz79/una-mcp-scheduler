# Mock Banner API Source of Truth

Record prepared: 2026-11-01. Repository snapshot inspected: `main` at
`220e3252bfb68ac478d2f9f407a70a68ff8e8c35` (PR #22 merge).

This is the evidence-based handoff for William's Mock Banner API work in the
UNA MCP Scheduling Research Project. The scoped Mock Banner API MVP is
**complete, pending integration feedback**, as recorded in the development
conversation. This is component completion, not full-system acceptance.

## Evidence and interpretation

Use these labels when extending this record:

- **CONFIRMED**: supported by inspected source, Git history, a recorded result,
  or an explicit project boundary. State which evidence supports the claim.
- **WORKING ASSUMPTION**: a provisional interpretation or proposed contract
  awaiting confirmation by the responsible workstream.
- **OPEN QUESTION**: an unresolved decision, discrepancy, or missing result.
- **RECOMMENDATION**: a proposed next step; not evidence that work occurred.

Evidence used for this version:

- The development conversation titled *Split MCP Server Workstreams*, including
  William's pasted commit/push/merge-sync output and the final assistant summary.
  The retrieved record contains summarized manual/testing results; original
  manual HTTP transcripts, the historical pytest terminal output, and attached
  image contents were not available. Keep that provenance when citing results.
- [API source](../app/main.py), [regression tests](../tests/test_api.py),
  [synthetic datasets](../data/), [runtime dependencies](../requirements.txt),
  [development dependencies](../requirements-dev.txt), and local Git history.
- [Initial data-model design](mock-data-model.md), which contains proposed
  fields/rules as well as confirmed boundaries. Current JSON and API source
  determine implemented fields and behavior.
- [Workstream 3 integration contract](workstream3-integration-contract.md) and
  [integration test checklist](workstream3-integration-test-checklist.md).
  The contract identifies itself as a proposal awaiting owner confirmation;
  it is not proof of MCP-to-API integration acceptance.

Local Git history confirms the milestones below. No remote fetch or fresh
GitHub status check was performed for this document. A historical clean working
tree or passing run must not be described as a permanent repository property.

## Architecture and phase boundary — CONFIRMED

```text
Student
  -> AI Assistant/Agent
     -> MCP Server
        -> Mock Banner HTTP API
           -> synthetic university data (JSON files)
```

This is the intended project chain. The API provides the academic-data service;
the MCP server exposes tools that obtain that data; the assistant requests and
explains structured results. The HTTP API and MCP server are separate components.
An API test or fake-MCP demonstration does not establish that the complete chain
has been connected and accepted.

Deterministic application logic is responsible for academic rules: prerequisite
and corequisite checks, capacity, time conflicts, credit limits, and validation
of proposed schedules. The language model must not independently decide academic
validity. The broader repository places planning and validation code in
`ai-agent/agent/planner.py` and `ai-agent/scheduling/validators.py`, as described
by the Workstream 3 contract. These responsibilities are not implemented by
the Mock Banner retrieval handlers themselves.

All records in this phase are synthetic. There is **no real UNA Banner
connection in this phase**, and these results do not demonstrate production
Banner interoperability or access to real student records. The purpose is a
controlled, repeatable environment for developing and testing the scheduling
prototype. A future UNA-approved backend replacement is a design goal, not a
completed integration or a claim of compatibility with Banner's native API.

## Implemented service — CONFIRMED from source

`app/main.py` defines a Python FastAPI application titled `UNA Mock Banner API`,
version `0.1.0`. Uvicorn is the runtime server dependency. Handlers load JSON
from the repository's `data/` directory and return records or filtered lists.
The application defines read-only `GET` routes and uses `HTTPException` for
missing-resource responses. FastAPI's default `/docs` and `/openapi.json`
interfaces are enabled.

| Method | Route | Supported query parameters | Result |
|---|---|---|---|
| GET | `/health` | None | `{"status":"ok","service":"UNA Mock Banner API"}` |
| GET | `/students` | None | Student list |
| GET | `/students/{student_id}` | None | One student; 404 if absent |
| GET | `/students/{student_id}/course-history` | None | That student's history; 404 if student absent |
| GET | `/students/{student_id}/enrollments` | None | That student's enrollment rows; 404 if student absent |
| GET | `/courses` | None | Course list |
| GET | `/courses/{course_id}` | None | One course; 404 if absent |
| GET | `/sections` | `course_id`, `term_id` | Section list, optionally filtered |
| GET | `/sections/{section_id}` | None | One section; 404 if absent |
| GET | `/course-history` | `student_id`, `status` | History list, optionally filtered |
| GET | `/enrollments` | `student_id`, `status` | Enrollment list, optionally filtered |
| GET | `/terms` | None | Term list |
| GET | `/terms/{term_id}` | None | One term; 404 if absent |

Filter comparisons use exact string equality. Supplying both supported filters
requires both to match. Omitted or empty-string filters are not applied.
No matching rows produce HTTP 200 with `[]`; collection filters do not validate
whether a supplied student/course/term exists. Student-specific nested routes
first verify the student exists, so an unknown student produces 404 rather than
an empty list. Existing students with no matching nested rows receive `[]`.

Missing-resource JSON has the form `{"detail":"Student not found"}`,
`{"detail":"Course not found"}`, `{"detail":"Section not found"}`, or
`{"detail":"Term not found"}`, as appropriate. These HTTP errors are not
already MCP structured error results.

There is no enrollment `term_id` filter, course text/subject search parameter,
registration operation, or schedule-validation endpoint in this API snapshot.
Do not describe MCP tool names from another workstream as HTTP routes.

## Implemented data model — CONFIRMED from `data/*.json`

Counts describe this snapshot, not required production sizes or schema guarantees.

| Entity / file | Rows | Fields present |
|---|---:|---|
| Student / `students.json` | 3 | `student_id`, `display_name`, `program`, `max_credit_hours`, `active` |
| Course / `courses.json` | 6 | `course_id`, `subject`, `course_number`, `title`, `credit_hours`, `prerequisites`, `corequisites` |
| CourseHistory / `course_history.json` | 6 | `student_id`, `course_id`, `term_id`, `grade`, `status` |
| Term / `terms.json` | 4 | `term_id`, `name`, `start_date`, `end_date` |
| Section / `sections.json` | 5 | `section_id`, `course_id`, `term_id`, `section_number`, `modality`, `capacity`, `enrolled_count`, `meetings` |
| Enrollment / `enrollments.json` | 2 | `student_id`, `section_id`, `status` |

A section belongs to a course and term. Enrollment links a student to a section;
its course and term are obtained through that section. Course history links a
student to a course and term. Course prerequisites/corequisites reference course
IDs. Meeting objects contain `days`, `start_time`, `end_time`, and `location`.
These are conceptual links in JSON, not database-enforced foreign keys.

The fixtures include active/inactive students; completed/failed history;
prerequisite chains; a full section (`SEC1002`, 30/30); an online section with
no meetings (`SEC2002`); existing enrollments; and overlapping meetings
(`SEC1001` and `SEC2001` on MON/WED). All current sections belong to `2027SP`.
Current corequisite arrays are empty. History statuses observed are `completed`
and `failed`; enrollment status observed is `enrolled`. Examples of other statuses
in the design document are not evidence of populated records or enforced enums.
The synthetic names, course details, and term dates are not official UNA data.

## Git and PR milestones — CONFIRMED from local history

Dates below are Git commit dates. They are not manual-test dates. PR numbers
come from merge commit subjects. Initial design/data commits have author label
`MCP Server`; do not infer a human author from that label.

| Date | Commit | Milestone / attribution | PR / merge where known |
|---|---|---|---|
| 2026-10-05 | `16d7551` | Initial data-model design; author label `MCP Server` | Not established here |
| 2026-10-05 | `e640772` | Initial synthetic dataset; author label `MCP Server` | Not established here |
| 2026-10-18 | `7c88ab8` | William: initial Mock Banner API and students endpoint | Not established here |
| 2026-10-23 | `b03db0b` | William: student detail and 404 handling | #15 / `9bfd07a` |
| 2026-10-23 | `c387889` | William: course list/detail | #16 / `c658d0a` |
| 2026-10-23 | `8af5857` | William: sections and filtering | #17 / `e2a22d1` |
| 2026-10-23 | `c736a5a` | William: course history and filtering | #18 / `581ccb1` |
| 2026-10-25 | `b025820` | Bryson Black: regression-test baseline | #19 / `174c7d3` |
| 2026-10-25 | `0c4a545` | William: enrollments and filtering | #20 / `dfc4d24` |
| 2026-10-25 | `4382387` | William: term endpoints | #21 / `be1a11d` |
| 2026-10-26 | `9870d0a` | William: final tests and documentation | #22 / `220e325` |

The final branch was `feature/banner-api-finalization`. Commit `9870d0a`
changed `README.md` and `tests/test_api.py` (243 insertions, 25 deletions).
William's pasted terminal output confirms its push, switching to `main`, pulling
from `be1a11d` to `220e325`, a clean working tree at that point, and deletion
of the local finalization branch. Git history corroborates the PR #22 merge.
No reviewer identity, review discussion, CI result, or exact merge time is
established by that terminal record.

Attribute William's API implementation and final test expansion accurately;
retain Bryson Black's baseline testing contribution. Do not assign all repository
work, agent evaluations, or initial dataset authorship to William.

## Verification record

### Manual verification — CONFIRMED as reported in the conversation

The final conversation summary records successful manual checks through direct
HTTP requests and FastAPI Swagger/OpenAPI: normal list/detail retrieval,
supported filters, valid identifiers, missing identifiers/404 responses, and
empty-result cases. It records no unresolved manual API failure.

This is a historical summary, not a new manual run performed while writing this
document. Exact request/response bodies, per-case timestamps, and original screen
captures are not available in the retrieved record. Do not invent them or claim
every filter permutation was manually tested. Source inspection confirms the
implemented behaviors separately from the reported observations.

### Automated regression testing — CONFIRMED historical result

**28 tests collected; 28/28 passing.** The conversation reports Python 3.13.13,
pytest 9.1.1, and one non-failing Starlette/httpx deprecation warning. It describes
an original 19-test baseline followed by expansion for enrollment and term
functionality. The baseline commit is attributed to Bryson Black; finalization
is attributed to William. The exact historical run time and raw pytest output
are not available in the retrieved conversation.

`tests/test_api.py` uses pytest and FastAPI `TestClient`. Its parametrized cases
account for the 28 tests: health (1), six list routes (6), four valid detail
lookups (4), four missing-resource cases (4), section filters (3), history
filters (3), student-specific history and missing student (2), enrollment filters
(3), and student-specific enrollments and missing student (2).

This suite exercises the ASGI application in process. It is not a live Uvicorn
HTTP transport test, an MCP-server test, an AI evaluation, a load test, or proof
that academic-rule validation is implemented by the API. Empty-result behavior
is evident in source but is not explicitly covered by a dedicated case in this
suite. Do not inflate these results with test counts from `ai-agent/`.

### Fresh component verification — CONFIRMED, 2026-11-01 (America/Chicago)

While preparing this record, the existing local environment ran:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_api.py -q -p no:cacheprovider
```

Result: **28 passed, 1 warning in 0.75s**, against the API/tests at `220e325`.
Python was 3.13.13; installed packages were pytest 9.1.1, FastAPI 0.146.0,
Starlette 1.9.0, and httpx 0.28.1. Plugin autoload and cache writing were disabled
for this run. The duration is recorded output, not a performance benchmark.
No dependencies or application/test files were changed. This rerun confirms
the current component suite; it does not close the integration items below.

### Known warning — CONFIRMED; resolution OPEN

The historical run passed with one Starlette/httpx deprecation warning. The
retrieved conversation does not retain its exact text. The fresh run above
emitted `StarletteDeprecationWarning`, reported at `fastapi/testclient.py:1`:

> Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.

The warning did not fail the suite. No dependency fix was applied or tested;
the message is an observation, not an instruction to change dependencies
without checking compatibility. The historical summary and fresh warning
remain separate evidence records.

## Reproduction commands — RECOMMENDATION

From the repository root in PowerShell, for a new development environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The default local server exposes `http://127.0.0.1:8000/docs`,
`http://127.0.0.1:8000/openapi.json`, and `/health`. Run the component suite
in another terminal:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api.py
```

These commands follow the current source/dependency files; listing them does
not assert that installation or live-server verification was performed for this
document. Runtime requirements are `fastapi` and `uvicorn[standard]`; development
requirements include those plus `pytest>=8,<10` and `httpx>=0.28,<1`.
They are not a fully pinned historical environment.

## Limitations — CONFIRMED scope/source boundaries

- Static synthetic JSON and read-only retrieval; no database transactions,
  registration persistence, or `POST`/`PUT`/`DELETE` operations.
- No declared Pydantic response models, strict record-schema enforcement,
  authentication, or authorization in `app/main.py`.
- No production-hardening claim: pagination, rate limiting, monitoring,
  deployment readiness, scale, and security acceptance are not demonstrated
  by the 28-test result.
- No complete Banner simulation, real Banner connector, degree audit, or
  complex prerequisite/degree-rule implementation in the Mock Banner API.
- Full MCP-to-Mock-Banner and student-to-agent acceptance remains open in this
  record. Agent tests using a fake MCP server do not close it.

## Open integration and documentation items

These are **OPEN QUESTIONS**, with proposed actions explicitly marked as
**RECOMMENDATIONS**. They do not mean the scoped retrieval MVP was unfinished.

| Item | Evidence / unresolved point | Recommended next action |
|---|---|---|
| MCP-to-HTTP acceptance | No accepted run through the actual MCP server and this HTTP API is established here. | Run the intended chain with synthetic data; retain component commits, configuration without secrets, requests, expected/actual results, and sign-off. |
| Enrollment shape and term handling | API returns enrollment links without `term_id`; WS3 proposes `get_student_enrollments(student_id, term_id)` returning full section objects. | Agree whether the MCP adapter joins sections and filters term/status, or an API change is required. Do not claim either implementation exists. |
| Course search | API lists courses; WS3 proposes `search_courses(query, subject)`. | Confirm where search/filter translation belongs and test it. |
| Error mapping and identity | API returns HTTP 404/detail; WS3 proposes MCP tool errors and structured `error_code`, plus connection-bound identity checks. API itself has no authorization. | Confirm MCP/identity ownership and verify error translation and student isolation at integration. |
| Data contract | WS3 requires JSON booleans and arrays of course IDs; current fixtures use them, without API schema enforcement. | Confirm formats/status meanings and test actual adapter outputs. |
| Scope of academic rules | Initial data-model document proposes simple all-required prerequisites/corequisites; this API only serves the fields. | Confirm rule policy with the deterministic-logic workstream before making academic-validity claims. |
| README discrepancy | Conversation says setup, runtime, endpoints, and tests were documented; inspected README at `220e325` stops inside the project-tree code block and lacks those sections. | Reconcile/complete README in a separate documentation update; record what changed. Do not repeat the historical completeness claim as a verified current fact. |
| Warning follow-up | The fresh run reproduces the exact warning above; no fix is verified. | Assess a compatible dependency update separately and retain before/after test results. |

The linked WS3 contract is a proposal, and its integration checklist contains
separate sign-off areas. Neither the proposal nor a fake-server baseline is
evidence of completed API integration.

## Research log

Keep observations, assumptions, questions, and advice separate. The entries
below were recorded on 2026-11-01; implementation dates appear in the Git table.

### CONFIRMED

- **C1 — Boundary:** synthetic data only; no real UNA Banner connection in this
  phase. Basis: explicit project framing, README, and data-model document.
- **C2 — Component:** the read-only API routes and six JSON entities above are
  implemented. Basis: inspected source/data at `220e325`.
- **C3 — Contribution:** William implemented the listed API milestones and
  final expansion/documentation; Bryson Black authored the baseline regression
  tests. Basis: Git authors and commit subjects, plus finalization transcript.
- **C4 — Results:** historical manual checks were reported successful and the
  final component regression result was 28/28 passing with one warning.
  Basis: conversation summary; preserve the raw-evidence limitation above.
  A separate 2026-11-01 local rerun also passed all 28 tests with one warning;
  its command, package versions, and exact warning are recorded above.
- **C5 — Finalization:** PR #22 merged as `220e325`; William synchronized local
  `main` and removed the local feature branch. Basis: Git and pasted output.

### WORKING ASSUMPTION

- **A1 — Adapter contract:** the WS3 proposal can guide MCP integration, but
  tool shapes, joins, search, errors, and ownership still need confirmation.
- **A2 — Initial rules:** simple all-required prerequisite/corequisite semantics
  are the initial data-model assumption, not a confirmed institutional policy
  or an API enforcement capability.
- **A3 — Replacement:** a stable interface is intended to permit a future
  approved backend; compatibility and approval remain unproven.

### OPEN QUESTION

- **Q1:** When will an actual MCP-to-HTTP integration run and full-chain
  acceptance be recorded, and against which component commits?
- **Q2:** Who owns the enrollment join/term filter, course search, error mapping,
  and identity enforcement decisions listed above?
- **Q3:** Does team/professor scope require any rules or schemas beyond the
  completed retrieval MVP? No additional assignment is established here.
- **Q4:** How should the README discrepancy and dependency warning be resolved?

### RECOMMENDATION

- **R1:** Prioritize integration support and retained acceptance evidence.
- **R2:** For each new observation, record date/time zone, component commits,
  command or request, expected/actual result, and an evidence-file reference.
- **R3:** Preserve historical results when adding a new run; identify changed
  dependencies/data and do not silently replace the 28/28 milestone.
- **R4:** Add schema, persistence, authentication, or more complex academic rules
  only when agreed scope or integration evidence calls for them.

## Instructions for a continuing AI assistant

Read this file, current source/tests, the data-model design, and the integration
contract before documenting William's work. Cite repository paths and commits
for implementation claims, and identify conversation-reported results as such.
If current code conflicts with a prior summary, preserve the historical account
and record the discrepancy rather than inventing a reconciliation.

Do not turn a recommendation into completed work, a proposed contract into team
agreement, source inspection into an executed test, a component pass into
end-to-end acceptance, or synthetic data into institutional records. Preserve
contributor attribution. Do not invent PR numbers, reviewers, dates, responses,
benchmarks, or warning fixes. Keep private conversation links/IDs, credentials,
and real student information out of repository documentation.

For a new research-log entry, use: `date | label | claim/decision | component
commit(s) | evidence | limitation or next action`. Change an item's label only
when new evidence supports it. This file records the Mock Banner workstream;
other workstreams' results must retain their own scope and attribution.
