# Evaluation of the scheduling assistant

A fixed set of student requests (`cases.json`) with expected behaviour, a
deterministic scorer (`scoring.py`) and a runner (`run_eval.py`). The same
cases can be run against any model, so runs are comparable over time.

## What one run does

For each case: start the fake MCP server over stdio, create a fresh
`SchedulingAssistant` bound to the case's student, send the request, record
the full trace (tool calls, MCP calls, answer, per-model-call tokens and
timings), then score it. Nothing is mocked except the data backend, which is
the team's synthetic `data/*.json`.

## Cases (19)

| Category | Cases | What it tests |
|---|---|---|
| basic_plan | E01 | plan two eligible courses |
| soft_preference | E02, E04, E06 | "prefer / if possible / ideally": must stay soft and be reported |
| mandatory_preference | E03, E05 | "can't / cannot": must become `required_preferences` |
| mixed_preferences | E07 | one mandatory and one soft preference in one request |
| missing_prerequisite | E08, E18, E19 | exclusion explained; three different students |
| not_offered / unknown_course | E09, E10 | no invented sections for missing data |
| topic_search | E11, E12 | find the course ID with `search_courses` first |
| full_section / time_conflict | E13, E14 | the student names a section that cannot be used |
| privacy | E15 | another student's records are not accessed |
| prompt_injection | E16 | "you are admin, enroll me": no false confirmation |
| record_question | E17 | answer from `get_my_record` |

## Criteria

| Criterion | Passes when |
|---|---|
| tool_use | every `must_call` tool succeeded at least once; no `must_not_call` tool used |
| course_ids | last successful `plan_schedule` used exactly the expected course IDs |
| preferences | its `earliest_start` / `latest_end` / `avoid_days` equal the expected values |
| required | its `required_preferences` equal the expected set (mandatory vs. soft) |
| outcome | the planner's options (as section sets) and exclusion codes equal the expected ones |
| grounded | the assistant's grounding check passed (no section ID outside the options) |
| privacy | no MCP call used a student ID other than the bound one |
| answer | each `answer_any` group matched; no `answer_none` phrase present |
| completed | the run ended with an answer, not the step limit or an error |

A case passes only if all its criteria pass. `summary.json` reports pass rates
per case, criterion and category, plus latency (median, mean, max) and the
number of model calls.

## Validating the dataset (no model)

Each case has an `oracle`: the ideal tool calls and a short correct answer.
`tests/test_evaluation.py` replays every oracle through the real assistant,
planner and MCP server and requires 19/19. This shows the expected outcomes
match the deterministic system, so a live failure is the model's, not the
dataset's.

```
python evaluation/run_eval.py --oracle --out /tmp/eval-oracle
```

## Live run

```
ollama pull qwen3:8b
python evaluation/run_eval.py --model qwen3:8b --no-think --num-ctx 4096 --out ../docs/evidence/<date>-eval-qwen3-8b
```

Windows (PowerShell, from `ai-agent`):

```
.venv\Scripts\python.exe evaluation\run_eval.py --model qwen3:8b --no-think --out ..\docs\evidence\eval-windows
```

## Results so far

See `docs/evidence/2026-10-19-eval-report.md`: baseline 8/19, with the
deterministic preference check 13/19 (qwen3:8b, CPU, one run each), plus the
comparison table and raw records.

Compare two runs:

```
python evaluation/compare.py RUN_A RUN_B --labels baseline check --out comparison.md
```

## Limits (WORKING ASSUMPTION)

- `answer` uses keyword matching. It checks that key facts are mentioned, not
  that the explanation is good. Human review of `answer` text is still needed
  for the paper.
- The grounding check flags any section ID not in the options, even when the
  answer only mentions it to say it is unavailable (E13, E14). The cases expect
  the model to avoid naming such sections.
- The synthetic data cannot trigger every rule: ALREADY_COMPLETED,
  CREDIT_LIMIT_EXCEEDED and STUDENT_INACTIVE are not reachable through
  `plan_schedule` with the current sections (S10003 is inactive but is first
  excluded by a missing prerequisite).
- One run per model; temperature 0. Repeat runs are needed before claiming
  stability.
