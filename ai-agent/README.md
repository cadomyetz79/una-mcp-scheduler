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
│   ├── assistant.py    # LLM tool-calling loop + guardrails
│   ├── evidence.py     # deterministic evidence rules for answers (claims, sections, named sections)
│   ├── preference_language.py  # how strongly the student states each time/day wish
│   ├── constraints.py  # time/day limits read from the student's words (enforced, or asked about)
│   ├── security.py     # trust boundaries: input inspection, tool-data filter, output guard
│   └── safe_answer.py  # deterministic answers when the model's answer cannot be shown
├── prompts/
│   └── system.md       # system prompt
├── dev/
│   ├── fake_mcp_server.py  # stand-in MCP server over data/*.json (until Workstream 2's is ready)
│   ├── stdio_server.py     # launches it over stdio with a chosen data folder (--data-dir / UNA_DATA_DIR)
│   ├── prepublish_check.py # privacy check before pushing or posting (see CLAUDE.md)
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

Not built yet: Entra identity (student_id is currently passed in) and the
connection to the real Mock Banner API / MCP server. Team handoff (status,
open PRs, integration requirements, how to run `heldout2`):
`docs/workstream3-handoff.md`. Integration-readiness audit and the fixes on
`fix/integration-readiness`: `docs/workstream3-integration-audit.md`.

## Architecture so far

```
student request ──> agent/assistant.py  (LLM: interprets + explains)
                          │ tools: get_my_record, search_courses, plan_schedule
                          │ guardrails: bound identity, arg + ID-schema checks, grounding,
                          │ evidence rules, trust boundaries + output guard, step limit
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
| `get_student_enrollments` (optional, proposed 2026-10-19) | `student_id`, `term_id` | sections the student is already registered in, as full `sections.json` records |

Errors are returned as MCP tool errors (`is_error: true`), not crashes,
ideally with a structured `error_code` (`"NOT_FOUND"`) and without internal
details in the text. The agent never shows error text to the model or the
student (it keeps only a hash). If the enrollments tool is missing, answers
say that current registrations could not be checked.

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
- ~~Should preferences like "no Fridays" be hard filters or soft rankings?~~
  Resolved by the 2026-10-19 entry below: both, chosen per preference.

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

### 2026-10-19 — Soft preferences and ranking (branch `feature/soft-preferences-ranking`)

Audit baseline: `main` @ `35f1b12`, rerun in the cloud: 41 passed, 1 skipped.
Gap found against the Workstream 3 requirements: every preference was a hard
filter and options were not ranked; a schedule that missed a wish was
silently not offered.

**CONFIRMED (tests run in the cloud, Linux, Python 3.13)**
- `Preferences.required` lists which of `earliest_start`, `latest_end`,
  `avoid_days` are mandatory. Required ones still filter sections (so the
  old behaviour is kept when `required` is left at its default). Anything
  else is soft: it never invalidates a schedule.
- Valid schedules are ranked by number of missed soft preferences, then by
  total minutes missed; ties keep enumeration order. Each option carries
  `rank`, `meets_all_preferences` and `preference_violations`.
- Ranking now happens over all valid combinations before cutting to
  `max_options` (before, the first 5 found were returned). The result reports
  `total_valid_options`, `options_truncated` and `search_capped` (search hit
  `MAX_COMBINATIONS`).
- Assistant tool `plan_schedule` gained `required_preferences`; its default
  is soft. The system prompt tells the model to use it only for "must/can't".
  Grounding is unchanged (section IDs still must come from an option).
- 52 passed, 1 skipped (+11 tests: `tests/test_ranking.py`, 2 new and 1
  changed in `tests/test_assistant.py`). Raw output:
  `docs/evidence/2026-10-19-ai-agent-soft-prefs-pytest-cloud.txt`; soft demo
  (`--earliest 10:00 --soft`): `docs/evidence/2026-10-19-ai-agent-soft-prefs-demo.json`.

**Behaviour change (deliberate)**: through the assistant, `earliest_start`
etc. are now soft unless listed in `required_preferences`.
`test_preferences_are_passed_to_planner` was renamed
`test_required_preferences_are_hard_filters` and passes `required_preferences`.

**NOT VERIFIED**
- Not run on Windows or in GitHub Actions yet (the branch is not pushed).
- Not run with a real LLM: whether qwen3 picks `required_preferences`
  correctly is untested.

**WORKING ASSUMPTION**
- Ranking order (count of misses, then minutes) is a simple default, not a
  team decision. `avoid_days` misses count 1 and add 0 minutes.
- One `required_preferences` list applies to the whole request.

**OPEN QUESTION**
- Should the student's wishes be weighted (for example "no Fridays" matters
  more than "after 10")? Current ranking treats each miss equally.

### 2026-10-19 — Live Ollama runs and evaluation (branch `feature/ollama-live-eval`)

**CONFIRMED (live model, raw records in `docs/evidence/`)**
- Ollama 0.40.6 runs qwen3:8b in the cloud sandbox on CPU. Default settings
  were killed by the 5.84 GiB memory limit; context 4096 with a q8_0 KV cache
  works (`2026-10-19-ollama-environment-and-first-runs.md`).
- `OllamaLLM` gained `think` (False turns off qwen3 reasoning; ~190 extra
  tokens even for "OK" otherwise) and `num_ctx`, and records tokens and
  timings per model call. `dev/chat.py` has `--no-think`, `--num-ctx`.
- `evaluation/`: 19 fixed requests, a deterministic scorer, a runner with
  `--resume` / `--summarize-only` / `--no-preference-check`, and
  `compare.py`. The oracle (ideal tool calls, no model) scores 19/19 in the
  tests; that validates the dataset only.
- Baseline (no check): **8/19** cases; the model classified mandatory vs.
  soft preferences correctly in 1 of 6 requests that state one, wrong in both
  directions.
- `agent/preference_language.py` + assistant: the student's own wording, per
  preference, corrects the model's mandatory/soft choice when it is clear;
  ambiguous or conflicting wording changes nothing. With the check:
  **13/19**; applied classification 7/7; no new errors; model tool calls
  identical to the baseline in all 19 cases.
- Both runs: 0 hard-constraint violations among returned options; grounded
  18/19; latency median 143 s (baseline) and 154 s (check) per case.
- Rejected tool arguments now get a specific message (`b394782`). A single
  live rerun of E14 still fails: the model promised to check and stopped.

**OPEN / NEXT** (details in `docs/evidence/2026-10-19-eval-report.md`)
- In 5 of 6 remaining failures the model ends its turn without calling
  `plan_schedule`. Proposed: a deterministic planning-required check.
- E09: the model said a course is offered when it is not; the grounding
  check only covers section IDs.
- The preference rules were written alongside the cases; real student
  wording is needed before claiming accuracy. One run per configuration.

### 2026-10-19 — Evidence orchestration and claim grounding (branch `feature/evidence-orchestration`)

**CONFIRMED (live model, one run; `docs/evidence/2026-10-19-eval-report-evidence.md`)**
- Diagnosis of the six remaining failures: four times the model answered from
  the catalog without `plan_schedule` (two with false availability claims),
  once after an invalid argument, and E16 was a correct refusal counted as
  ungrounded by the section rule.
- `agent/evidence.py`: a request about taking/planning/availability with
  known course IDs needs plan evidence; one nudge, then at most one
  system-run `plan_schedule` (only when the request states no time/day
  wishes); availability/eligibility claims need plan evidence; a section the
  student named may be mentioned while rejecting it.
- Live, same 19 cases and settings: **19/19** (from 13/19). All five
  missing-plan cases recovered after one nudge, with the model's own correct
  `plan_schedule` call; the system-run fallback was not needed. No new
  failures; 0 unsupported availability claims in final answers (from 2);
  0 hard-constraint violations. Cost: 9 more model calls in total, mean
  latency 143 s → 200 s per case.

**LIMITS**
- Rules written after reading these failures; one run; fallback path tested
  only with scripted responses. E16 passes because the rule changed (same
  answer); E14 passes partly through keyword scoring ("no conflicts").
  Dataset v2 with unseen requests is the next step.



### 2026-10-19 — Held-out evaluation (branch `feature/heldout-evaluation`)

**CONFIRMED (live, qwen3:8b, CPU; `docs/evidence/2026-10-19-heldout-report.md`)**
- New held-out set: 34 requests with their own data, pre-registered in
  `6429394` before any run; scoring v2 with sentence-level assertions (the
  E14 "no conflicts" weakness is fixed; development final system 19/19 ->
  18/19 under v2.1).
- Two complete runs (plus retries of infrastructure failures): 25/34 each,
  identical pass/fail and tool calls in all 34 cases. 0 false or
  unsupported academic claims, 0 hard-constraint violations, tool-call
  correctness 27/27, grounded 33/34.
- Failures: three prompt injections succeed (bare "confirmed", system
  prompt printed, fake tool result accepted), section IDs used as course
  IDs, an unstated conflict, the deterministic check overriding a correct
  model reading (H32), and three scoring-strictness cases.
- The system-run fallback ran live once (H22, missing student record) and
  reported the limitation correctly; scripted tests cover the other paths.
- Infrastructure: model calls up to 870 s and four out-of-memory crashes of
  the model server on the 5.84 GiB sandbox.

**LIMITS**: one model, CPU, two runs, synthetic English data; the dataset
author also wrote the rules (H32 documented).

### 2026-10-19 — Security hardening (branch `feature/security-hardening`)

**CONFIRMED (tests and live development runs; `docs/evidence/2026-10-19-security-report.md`)**
- The 34-case held-out set is development data from here on (`8f95f8e`); a
  new 37-case held-out set (`evaluation/heldout2/`, own ITM data) was
  pre-registered for future generalisation claims and has not been run.
- Trust boundaries in code (`agent/security.py`): input inspection, fake
  tool output / system markers labelled as student text, instruction-like
  tool data removed before the model sees it, output guard against
  instruction/tool-definition leaks (fixed refusal; logs keep length + hash),
  and answers still unverified after one revision are replaced by an answer
  built from tool results (`agent/safe_answer.py`) instead of being returned
  flagged.
- Academic correctness: course vs section ID schemas (H15); the student's
  named sections are validated as one combination and an unstated conflict
  gets a deterministic sentence (H14); relaxed wishes are "conflicting" and
  never override the model (H32); wishes the student never mentioned are not
  applied; prerequisite mentions are not claim subjects.
- Tests: 428 passed, 1 skipped (was 222 + 1). New-set input inspection
  (measured before any run): 5/10 attacks flagged, 0/27 false positives.
  Replay on 126 recorded live answers: 0 passing answers changed.
- Live, final code (development data): the six held-out failures 6/6,
  ten held-out controls 10/10, security live set 10/11 (scoring v2.2); no
  legitimate request blocked; a real partial prompt leak (H20) was blocked by
  the output guard. Deterministic checks cost < 1 ms per case.

**LIMITS**: keyword input inspection misses half of the new set's attacks;
paraphrased/translated leaks are not detected; single-turn only; one model on
CPU; rules and most tests written by the same developer. Not production-ready.

### 2026-10-19 — Integration-readiness fixes (branch `fix/integration-readiness`)

Audit and details: `docs/workstream3-integration-audit.md`.

**CONFIRMED (tests; no model was run)**
- D1/D3: backend errors become fixed messages with a category
  (`not_found`, `unknown_tool`, `tool_error`, `backend_unavailable`,
  `backend_data_error`); their text is never sent to the model, shown to the
  student or logged (hash only). Outages are no longer reported as "course
  does not exist".
- D2: any unexpected failure ends the run with a fixed answer,
  `stopped_reason="error"` and a category; `run_eval.py` maps the category to
  `error_kind`, so infrastructure retries still work.
- D4: `agent/constraints.py` reads time/day limits from the student's words
  and enforces them when the model leaves them out or gets them wrong; an
  unclear mandatory limit gets a fixed clarification question instead of a
  schedule. The system-run plan now runs with reliably read limits.
- D5/D6: per-request state in a run object; each result's MCP trace holds
  only its own calls (`BannerTools.run_log()`). Concurrency tests with
  different students and constraints fail on the old code and pass now.
- Current registrations: optional `get_student_enrollments` tool (fake
  server only); options that repeat, overlap or exceed the credit limit with
  current classes are flagged, ranked last and explained; "could not check"
  is said when the tool is missing.
- Tests: 478 passed, 1 skipped (was 428 + 1), Python 3.13 and 3.12.

**LIMITS**: not tested against any real WS1/WS2/WS4 component; constraint
reading is English and keyword based; options conflicting with current
registrations are flagged, not removed (team decision); still single-turn,
no partial schedules. Not integration-ready.

### 2026-10-20 — Quality pass (branch `fix/ws3-quality-pass`)

Details: `docs/workstream3-integration-audit.md` §10.

**CONFIRMED (tests; no model was run, `heldout2` not opened)**
- Current registrations: every option is labelled `fits_current_registration`,
  `requires_registration_change`, `not_confirmed` or `not_checked`. An answer
  that presents an option needing a change as fine (or claims options fit
  when that was not checked) gets a revision, then the fallback answer, which
  labels every option. Options are still never removed (team decision).
- Constraints: strength is read per fragment, so a wish next to a mandatory
  limit no longer weakens it; exceptions ("except on Tuesdays"), approximate
  times ("around 4"), alternatives ("9 or 10"), dash ranges, "9.30" and
  "10 at night" are handled; unclear mandatory limits are asked about.
- R7: `--data-dir` for `dev/chat.py` and `dev/demo_plan.py`, passed to the
  MCP subprocess. R9: per-request model statistics (`AssistantResult.llm_calls`).
- Publication privacy: `CLAUDE.md` rules and `dev/prepublish_check.py` (commit
  messages, added lines and PR texts; never prints what it finds;
  `--install-hook` for a local commit-msg hook).
- Tests: 582 passed, 1 skipped (was 478 + 1), Python 3.13 and 3.12.

**LIMITS**: a wish next to a mandatory limit of the same kind does not rank
options (one value per preference); clarification answers need conversation
history (R2) to be useful in a real chat. Not integration-ready.
