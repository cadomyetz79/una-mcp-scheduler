# AI Agent & Scheduling Logic (Workstream 3)

Owner: Hassan Alnabres · Branch: `feature/ai-agent`

## What is here

```
ai-agent/
├── scheduling/
│   ├── models.py       # Student, Course, Section, Meeting, CourseRecord
│   ├── validators.py   # deterministic academic-rule checks + validate_schedule()
│   └── loader.py       # loads data/*.json into models (dev/testing only)
├── tests/
│   ├── conftest.py
│   ├── test_mock_dataset.py   # scenarios using the team's data/ files
│   └── test_validators.py     # edge cases not in the dataset yet
└── requirements.txt
```

Not built yet: `agent/` (MCP client + LLM loop) and `prompts/`.

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
