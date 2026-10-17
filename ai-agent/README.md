# AI Agent & Scheduling Logic (Workstream 3)

Owner: Hassan Alnabres · Branches: `feature/ai-agent` (validator), `feature/ai-agent-mcp` (MCP client + planner + CI), `feature/ai-agent-llm` (LLM assistant)

## What is here

```
ai-agent/
├── scheduling/
│   ├── models.py       # Student, Course, Section, Meeting, CourseRecord
│   ├── validators.py   # deterministic academic-rule checks + validate_schedule()
│   └── loader.py       # loads data/*.json into models (dev/testing only)
├── agent/
│   ├── banner_tools.py # typed MCP client wrapper; TOOL_NAMES maps to server tool names
│   ├── planner.py      # deterministic schedule generation over MCP data
│   ├── llm.py          # LLM backends: OllamaLLM (local, free) and ScriptedLLM (tests)
│   └── assistant.py    # LLM tool-calling loop + guardrails
├── prompts/
│   └── system.md       # system prompt
├── dev/
│   ├── fake_mcp_server.py  # stand-in MCP server over data/*.json (until Workstream 2's is ready)
│   ├── demo_plan.py        # planner demo over stdio (no LLM)
│   └── chat.py             # full assistant demo over stdio with Ollama
├── tests/
│   ├── conftest.py
│   ├── test_mock_dataset.py   # scenarios using the team's data/ files
│   ├── test_validators.py     # edge cases not in the dataset yet
│   ├── test_mcp_planner.py    # agent <-> MCP tests, incl. one real stdio run
│   └── test_assistant.py      # LLM loop + guardrails with a scripted model
└── requirements.txt
```

Not built yet: Entra identity (student_id is currently passed in), and a
live-model evaluation run.

## Architecture so far

```
student request ──> agent/assistant.py  (LLM: interprets + explains)
                          │ tools: get_my_record, search_courses, plan_schedule
                          │ guardrails: bound identity, arg checks, grounding, step limit
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

Talk to the full assistant (needs [Ollama](https://ollama.com) running and
`ollama pull qwen3:8b`):

```bash
python dev/chat.py "I want CIS376 and CIS410, no classes before 10am"
python dev/chat.py --save ../docs/evidence/chat-run.json "Can I take the capstone?"
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

### 2026-10-05 — LLM assistant with guardrails

**CONFIRMED**
- `agent/assistant.py`: tool-calling loop. The model gets three tools
  (`get_my_record`, `search_courses`, `plan_schedule`); `plan_schedule` runs
  the deterministic planner, so the model never decides validity.
- Guardrails enforced in code: (1) student_id/term bound at creation, no tool
  accepts an ID, undeclared arguments rejected; (2) argument validation
  (course list, HH:MM times, day names) before anything reaches MCP;
  (3) grounding check — section IDs in the final answer must come from a
  `plan_schedule` option, one forced revision, then flagged
  `grounded=False`; (4) step limit.
- `agent/llm.py`: `OllamaLLM` (local open-source model over Ollama's
  `/api/chat`, default `qwen3:8b`, temperature 0) and `ScriptedLLM`.
- 41 tests passing, 1 skipped (live Ollama test, opt-in with
  `RUN_OLLAMA_TESTS=1`). The 11 new tests script the model's behavior,
  including trying another student's ID, malformed arguments, an unknown
  tool, an invented section ID, and an endless tool loop; each is caught by
  code. Output: `docs/evidence/2026-10-05-ai-agent-llm-pytest-cloud.txt`.

**WORKING ASSUMPTION**
- Ollama + `qwen3:8b` as the default model (free, runs locally). Any
  tool-calling model can replace it behind the same `chat()` interface.
- Section IDs match `SEC<digits>` for the grounding check.

**OPEN QUESTION**
- No real model has been run yet: Ollama could not be installed in the
  cloud test environment. First live runs should happen on a lab machine.
- Which model(s) to evaluate, and on what set of student requests? A fixed
  request set run through `dev/chat.py --save` would give comparable
  evidence (tool use, grounding rate, latency) for the paper.
- Does the team want Ollama (local, free) or a hosted API for the final
  system?
