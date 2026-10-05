# AI Agent & Scheduling Logic (Workstream 3)

Owner: Hassan Alnabres · Branches: `feature/ai-agent` (validator), `feature/ai-agent-mcp` (MCP client + planner)

## What is here

```
ai-agent/
├── scheduling/
│   ├── models.py       # Student, Course, Section, Meeting, CourseRecord
│   ├── validators.py   # deterministic academic-rule checks + validate_schedule()
│   └── loader.py       # loads data/*.json into models (dev/testing only)
├── agent/
│   ├── banner_tools.py # typed MCP client wrapper; TOOL_NAMES maps to server tool names
│   └── planner.py      # deterministic schedule generation over MCP data
├── dev/
│   ├── fake_mcp_server.py  # stand-in MCP server over data/*.json (until Workstream 2's is ready)
│   └── demo_plan.py        # end-to-end demo over stdio
├── tests/
│   ├── conftest.py
│   ├── test_mock_dataset.py   # scenarios using the team's data/ files
│   ├── test_validators.py     # edge cases not in the dataset yet
│   └── test_mcp_planner.py    # agent <-> MCP tests, incl. one real stdio run
└── requirements.txt
```

Not built yet: the LLM layer (turning a student's request into planner
arguments and explaining the result) and `prompts/`.

## Architecture so far

```
student request ──> [LLM layer: not built yet]
                          │ student_id, term, courses, preferences
                          ▼
                    agent/planner.py ──── validate_schedule()  (deterministic)
                          │
                    agent/banner_tools.py
                          │ MCP (stdio)
                          ▼
              dev/fake_mcp_server.py  →  later: Workstream 2's MCP server
                          │
                       data/*.json   →  later: Workstream 1's mock Banner API
```

Run the demo (from `ai-agent/`):

```bash
python dev/demo_plan.py S10001 2027SP CIS376 CIS410
python dev/demo_plan.py S10001 2027SP CIS376 CIS410 --earliest 10:00
```

### Proposed MCP tool contract (for Workstream 2)

WORKING ASSUMPTION — the fake server uses these; Workstream 2 owns the real names.

| Tool | Arguments | Returns |
|---|---|---|
| `get_student_record` | `student_id` | student object (`data/students.json` shape); error if unknown |
| `get_course_history` | `student_id` | list of `course_history.json` records |
| `get_course` | `course_id` | course object; error if unknown |
| `search_courses` | `query`, `subject` (both optional) | list of courses |
| `get_course_sections` | `course_id`, `term_id` | list of `sections.json` records |

Errors are returned as MCP tool errors (`is_error: true`), not crashes.

## Design rule

The LLM proposes a schedule as a list of section IDs. `validate_schedule()`
decides whether it is valid. The LLM never makes that decision; it only
explains the result or retries using the returned issue codes.

```python
from scheduling.loader import load_dataset
from scheduling.validators import validate_schedule

ds = load_dataset()
result = validate_schedule(ds.students["S10001"], ["SEC1001", "SEC2001"],
                           "2027SP", ds.sections, ds.courses)
result.to_dict()
# {'valid': False, 'total_credit_hours': 6, 'issues': [{'code': 'TIME_CONFLICT', ...}]}
```

## Checks and issue codes

| Code | Rule |
|---|---|
| `STUDENT_INACTIVE` | student `active` is false |
| `UNKNOWN_SECTION` / `UNKNOWN_COURSE` | ID not found in the data |
| `WRONG_TERM` | section is not in the requested term |
| `DUPLICATE_COURSE` | two sections of the same course |
| `ALREADY_COMPLETED` | course already completed |
| `MISSING_PREREQUISITE` | a listed prerequisite is not completed (AND rule) |
| `MISSING_COREQUISITE` | corequisite neither completed nor in the same schedule |
| `SECTION_FULL` | `enrolled_count >= capacity` |
| `TIME_CONFLICT` | two meetings share a day and overlap (back-to-back is allowed; no-meeting/online sections never conflict) |
| `CREDIT_LIMIT_EXCEEDED` | total credit hours > `max_credit_hours` |

## Run the tests

```bash
cd ai-agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -v
```

## Development log

### 2026-10-05 — Deterministic schedule validator

**CONFIRMED**
- Implemented models and validators against the field names in
  `docs/mock-data-model.md` and the JSON files in `data/`.
- 21 pytest tests, all passing (Python 3.13.16, pytest 9.1.1):
  10 scenario tests on the team dataset + 11 edge-case unit tests.
- Reproduced on Hassan's Windows laptop (win32, Python 3.12.10, pytest 9.1.1):
  21 passed. Raw output in `docs/evidence/2026-10-05-ai-agent-pytest-windows.txt`;
  cloud run in `docs/evidence/2026-10-05-ai-agent-pytest-cloud.txt`.
- Verified on the team dataset:
  - S10001, SEC1001 + SEC2002 → valid, 6 credit hours
  - S10001, SEC1001 + SEC2001 → `TIME_CONFLICT` (MON/WED 09:30–10:45 vs 10:30–11:45)
  - S10001, SEC1002 → `SECTION_FULL` (30/30)
  - S10001, SEC3001 → `MISSING_PREREQUISITE` (CIS450 needs CIS376 and CIS410)
  - S10002, SEC1001 → `MISSING_PREREQUISITE` (no CIS330)
  - S10003 → `STUDENT_INACTIVE`; failed CIS236 does not count as completed

**WORKING ASSUMPTION**
- Only `status: "completed"` satisfies a prerequisite. `in_progress`,
  `failed` and `withdrawn` do not.
- No minimum grade (a C or D still counts).
- Retaking a failed course is allowed; retaking a completed course is flagged.

**OPEN QUESTION**
- `course_history.json` marks S10001's CIS330 as `completed` in 2026FA,
  which runs until 2026-12-11. Should that be `in_progress`? If so, S10001
  is not eligible for CIS376/CIS410 yet under the current rule. (Workstream 1)
- S10001 is already enrolled in SEC1001 for 2027SP (`enrollments.json`).
  Should existing enrollments be added to a proposed schedule before
  checking conflicts and credit hours?
- Should `validate_schedule` be exposed as an MCP tool (Workstream 2), or
  stay inside the agent? It is pure Python with no I/O, so either works.
- Which LLM / agent framework will the agent use?

### 2026-10-05 — MCP client, fake MCP server, deterministic planner

**CONFIRMED**
- `dev/fake_mcp_server.py` serves `data/*.json` through 5 MCP tools, built
  with the MCP Python SDK 2.2.0 (`MCPServer`, stdio transport).
- `agent/banner_tools.py` reaches all academic data through MCP only and
  logs every tool call (`BannerTools.calls`) for evidence.
- `agent/planner.py` generates schedules deterministically: course-level
  checks (prerequisites, already completed, offered this term, open seats,
  preferences), then every section combination is checked with
  `validate_schedule()`. Only accepted combinations are returned.
- 30 pytest tests passing (21 previous + 9 new), including one that launches
  the server as a subprocess and talks MCP over stdio. Raw output in
  `docs/evidence/2026-10-05-ai-agent-mcp-pytest-cloud.txt`.
- Demo `S10001 2027SP CIS376 CIS410 CIS450` over stdio returned one option,
  SEC1001 + SEC2002 (6 credit hours); CIS450 excluded for
  `MISSING_PREREQUISITE`; SEC1001 + SEC2001 rejected for `TIME_CONFLICT`;
  8 MCP calls. Output in `docs/evidence/2026-10-05-ai-agent-mcp-demo.json`.

**WORKING ASSUMPTION**
- Tool names and shapes in the contract table above, until Workstream 2
  confirms or changes them (change `TOOL_NAMES` only).
- Planner requires all requested eligible courses together; it does not yet
  suggest dropping one course when no combination fits.

**OPEN QUESTION**
- If no combination of all requested courses works, should the agent offer
  partial schedules (e.g. best 2 of 3 courses)?
- Should preferences like "no Fridays" be hard filters (current behavior)
  or soft rankings?

### 2026-10-05 — Continuous integration (GitHub Actions)

**CONFIRMED**
- Added `.github/workflows/ai-agent-tests.yml`: runs the ai-agent tests on
  Ubuntu and Windows with Python 3.12 and 3.13 (4 jobs) on every push and
  pull request that touches `ai-agent/`, `data/` or the workflow.
- Each job uploads its full pytest output as an artifact
  (`pytest-<os>-py<version>`), which replaces manual test screenshots as
  evidence. The workflow's test step was dry-run locally (30 passed); the
  first real Actions run is recorded on the pull request.
