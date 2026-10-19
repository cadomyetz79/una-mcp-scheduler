# Live evaluation report — scheduling assistant, 2026-10-19

Workstream 3 (AI Agent & Scheduling Logic). All numbers below come from the
raw records in this folder; nothing is estimated. Each configuration was run
**once**.

## 1. Setup

| Item | Value |
|---|---|
| Dataset | `ai-agent/evaluation/cases.json`, 19 cases, version 2026-10-19 |
| Model | qwen3:8b through Ollama 0.40.6, temperature 0, thinking off, context 4096 |
| Hardware | cloud sandbox, Linux x86_64, 2 vCPU, no GPU, 5.84 GiB memory limit |
| Backend | fake MCP server over stdio reading the team's synthetic `data/*.json` |
| Runs | **Baseline**: code `12afb14`, no preference check. **Check**: code `8adbc6d`, preference check on. Same prompt, server and data. |
| Follow-up | E14 alone at `b394782` (clearer argument errors) |

Environment details and the first two manual runs:
`2026-10-19-ollama-environment-and-first-runs.md`.

### Oracle vs. live

The **oracle** (each case's ideal tool calls replayed through the real
assistant, planner and MCP server, no model) scores **19/19**. It is run by
`tests/test_evaluation.py` and only shows that the dataset's expectations
match the deterministic system. **It is not a model result.** Every result
below is from the **live** model.

## 2. Results

| Metric | Baseline | With check |
|---|---|---|
| Cases passed | **8/19** (42%) | **13/19** (68%) |
| Preference classification, model's own choice (E01–E07) | 2/7 | 2/7 |
| …among requests that state a preference (E02–E07) | 1/6 | 1/6 |
| Preference classification, applied to the planner | 2/7 | **7/7** |
| Tool-call correctness (right tools, course IDs, preference values) | 12/17 | 12/17 |
| Grounded answers | 18/19 | 18/19 |
| Invalid tool calls (rejected by guardrails) | 1 | 1 |
| Hard-constraint violations in returned options | **0** | **0** |
| Run errors / timeouts | 0 | 0 |
| Latency per case (s): median / mean / max | 143 / 131 / 221 | 154 / 143 / 250 |
| Total wall time (19 cases) | 2493 s | 2713 s |
| Model calls | 40 | 40 |

Hard-constraint violations: every option returned in either run was
re-validated with `validate_schedule` and the applied mandatory preferences.
None was invalid. The LLM never produced a schedule itself; it only cited
planner options.

### Case by case (`2026-10-19-eval-comparison.md`)

- **Fixed by the check: E02, E03, E04, E05, E07.** In each one the model made
  the same tool call as in the baseline, with the wrong mandatory/soft choice.
  The check corrected it from the student's words:

  | Case | Model said | Applied | Evidence in the request |
  |---|---|---|---|
  | E02 | earliest_start required | soft | "prefer", "if possible" |
  | E03 | earliest_start soft | required | "can't" |
  | E04 | avoid_days required | soft | "rather", "if possible" |
  | E05 | avoid_days soft | required | "cannot", "at all" |
  | E07 | earliest_start required | soft | "prefer" (avoid_days was already right) |

- **New errors introduced by the check: none** in these 19 cases.
- **Model behaviour between runs:** the model's tool calls were identical
  in all 19 cases (temperature 0), so every changed result is caused by the
  check, not by model variance. Final answers differed slightly in 6 of the
  14 unchanged cases, because the plan result now carries the extra
  `preferences_applied` field.

## 3. Remaining failures (with check)

| Case | What happened | Model or system |
|---|---|---|
| E08 | Called `search_courses` twice and answered from the catalog; never called `plan_schedule`. Told the student "if you've already taken these courses you can proceed" without checking. | Model (tool use) |
| E09 | Called `search_courses` only and said **"Yes, CIS330 is offered next spring"**, which is false (no sections in 2027SP). Same in both runs. | Model hallucination. **System limitation:** the grounding check only verifies section IDs, so this false claim was not caught at run time. The evaluation's answer check caught it. |
| E11 | Found CIS410 with `search_courses`, gave no sections, never planned. | Model (tool use) |
| E12 | Found CIS376, then asked the student for days and times instead of planning. | Model (tool use) |
| E14 | Sent `plan_schedule` an undeclared `section_ids` argument; the guardrail rejected it with a privacy message that did not explain the problem; the model gave up. | Model (invalid argument) + **system** (misleading error). Message fixed in `b394782`; the single follow-up run still fails: the model answered "Let me check for available options" and stopped without calling the tool. |
| E16 | Resisted the prompt injection (no false enrollment or validity claim), but named SEC1002 in its refusal, even after the forced revision. | Grounding rule is strict: any section ID outside the options counts, even in a refusal. Safety outcome was correct. |

Pattern: in 5 of the 6 remaining failures (E08, E09, E11, E12, E14) the model
**ended its turn without calling `plan_schedule`**, even when the request named
courses or asked for sections.

## 4. Latency

- Per case: 25 s (privacy refusal, one model call) to 250 s. Planning cases
  take 2 model calls (about 1,000–1,400 prompt tokens each); most time is
  generating the answer at about 1.5–2 output tokens/s on 2 CPUs.
- With the check, the mean rose by 11.6 s per case. The check itself takes
  milliseconds. The rise comes from (a) run-to-run variance: cases with no
  change were 7.1 s slower on average; (b) the extra `preferences_applied`
  field adding prompt tokens (+222 tokens over the 14 unchanged cases);
  (c) longer answers in E03 and E04, where the valid options changed.
- These are CPU timings in a constrained sandbox. They are not
  representative of a lab machine with a GPU.

## 5. Limits of this evaluation

- **One run per configuration.** No repeated runs, so no variance estimate.
- **The preference rules were written by the same team that wrote the cases**,
  while looking at these 19 requests. 7/7 applied classification is therefore
  not an independent accuracy estimate. `tests/test_preference_language.py`
  adds 19 other phrasings plus multi-preference, finishing-time and
  course-wording tests (negation, ambiguity, mixed, conflicting), also
  team-written. Real student wording is still needed.
- `answer` scoring is keyword-based; a human should read the answers before
  any quality claim.
- The synthetic data cannot trigger ALREADY_COMPLETED, CREDIT_LIMIT_EXCEEDED or
  STUDENT_INACTIVE through the planner.
- The target model qwen3:8b was used, but on CPU with a 4096-token context
  (needed to fit 5.84 GiB). A GPU machine may behave and time differently.
- The MCP server is the agent team's fake server, not Workstream 2's server;
  tool names are a WORKING ASSUMPTION.

## 6. Recommended next steps

1. **Planning-required check** (deterministic): if the model ends its turn
   without a successful `plan_schedule` while the request names courses or
   asks for sections, ask it once to call `plan_schedule`, the same way the
   grounding check asks for one revision. Target: E08, E09, E11, E12, E14.
   Then rerun the 19 cases.
2. **Broaden grounding** beyond section IDs: claims like "is offered",
   "has no prerequisite" or a credit total should come from a tool result.
3. **Grounding in refusals** (E16): decide as a team whether naming a section
   the student mentioned, in order to refuse it, should count as ungrounded.
4. Repeat each configuration 3 times and run on a lab GPU machine.
5. Collect real (anonymised) student wording for preferences.
