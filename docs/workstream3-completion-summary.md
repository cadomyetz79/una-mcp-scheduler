# Workstream 3 completion and handoff summary

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`), Workstream 3 (AI Agent & Scheduling Logic) |
| Date | 2026-11-01, `main` at `052336f` (updated from the 2026-10-28 `220e325` checkpoint) |
| Code | `ai-agent/` on `main` at `052336f`; Pydantic candidate `24e3fe1` deferred |
| PRs | WS3: #1, #2, #3, #5 to #14 (excluding #4), #23 to #28 and #30, all merged (2026-10-17 to 2026-11-01). WS2 protected MCP server: #29 (merged 2026-11-01). |
| Status | **Implemented WS3 prototype; offline regression passed on 2026-11-01 (Step 5).** The agent runs against WS2's protected MCP server (PR #29) over Streamable HTTP with a synthetic signed token in offline tests. No live Microsoft Entra login, no real Banner data, and no live-model evaluation of the current code. The `heldout2` live evaluation (Step 6) of the pre-registered code `d4eacbf` is **done**: 23/37 in both runs (`docs/evidence/2026-11-02-heldout2-report.md`). Not production-ready. |

Companion documents:

- `docs/workstream3-integration-contract.md`: what WS1, WS2 and WS4 must
  provide.
- `docs/workstream3-integration-test-checklist.md`: how to test the
  integration.
- `docs/workstream3-handoff.md`: development history and how to run
  `heldout2`.
- `docs/workstream3-integration-audit.md`: defect fixes D1 to D6 and the
  quality pass.

---

## 1. Verified features

| Feature | PR | Evidence |
|---|---|---|
| Deterministic validator: term, duplicates, completed courses, prerequisites (AND), corequisites, seats, time conflicts, credit limit, inactive student | #1 | `tests/test_validators.py`, `tests/test_mock_dataset.py` |
| MCP client (`BannerTools`), fake MCP server, deterministic planner | #2 | `tests/test_mcp_planner.py` |
| LLM assistant with code-enforced guardrails: bound identity and term, argument allow-list, step limit, grounding check | #3 | `tests/test_assistant.py` |
| Soft vs mandatory preferences and ranking | #5 | `tests/test_ranking.py` |
| Preference-strength check from the student's words; live evaluation tooling | #6 | `tests/test_preference_language.py`, `tests/test_evaluation.py` |
| Evidence rules: availability and eligibility claims need a planner result | #7 | `tests/test_evidence.py` |
| Held-out evaluation, 34 cases, pre-registered; scoring v2 and fallback when the model ignores the evidence nudge | #8 | `tests/test_heldout.py`, `tests/test_assertions.py`, `tests/test_fallback.py`, `docs/evidence/2026-10-19-heldout-report.md` |
| Trust boundaries, output guard, ID schemas, named-section checks; `heldout2` pre-registered | #9 | `tests/test_security.py`, `tests/test_security_assistant.py`, `tests/test_heldout2.py` |
| Handoff documentation | #10 | `docs/workstream3-handoff.md` |
| Safe backend and model failures (D1–D3), hard limits from the student's words (D4), per-request isolation (D5–D6), current registrations | #11 | `tests/test_integration_readiness.py` |
| Registration-fit labels, stricter reading of hard limits, data folder over stdio (R7), per-request model statistics (R9), publication privacy check | #12 | `tests/test_quality_pass.py`, `tests/test_prepublish_check.py` |
| Integration contract | #13 | `docs/workstream3-integration-contract.md`, `docs/workstream3-integration-test-checklist.md` |
| Strict field types: `active` only as a JSON boolean (G1); `prerequisites` / `corequisites` only as arrays of course IDs, also in search rows (G2); malformed values fail closed | #14 | `tests/test_strict_record_fields.py` (59 tests) |
| Handoff and P1 verification evidence | #23 | this document, `docs/workstream3-handoff.md` |
| H1: mandatory time and day limits also apply to sections the student names; day codes (`MWF`, `TR`, `Tu/Th`) are read as day names | #24 | `tests/test_mandatory_constraints.py` (44 tests) |
| M1: course search shows the model at most 20 courses, sorted by ID, with `total_matches` and `truncated` | #25 | `tests/test_search_limit.py` (29 tests) |
| Strict numeric and meeting data (data fixes F1 to F5): whole, non-negative counts; non-empty `days` arrays; ASCII 24-hour `HH:MM`; overflow is a data error | #26 | `tests/test_strict_numeric_fields.py` (158 tests) |
| Security audit F1, F3, F4, F6, F7: registration claims are unsupported; the evidence check stays on when another student's ID appears; availability claims need every named course; records with another `student_id` are rejected; messages over 4000 characters get a fixed answer, and the constraint reader no longer takes quadratic time | #27 | `tests/test_security_audit_fixes.py` (33 tests) |
| Security audit F12, F8: `plan_schedule` time arguments are checked with the planner's own parser; the constraint parse cache is per request | #28 | `tests/test_security_phase_b1.py` (17 tests) |
| WS2 protected MCP server (WS2-owned): six read-only tools, bearer token check, per-student access check (`FORBIDDEN`), structured `error_code` | #29 | root `tests/` (53 tests), `docs/workstream2-mcp-integration.md` |
| Security audit F2: meeting days, times and credit hours an answer gives for a planned section must match the `plan_schedule` result | #30 | `tests/test_section_details.py` (112 tests) |

Two numbering schemes are in use. "Data fixes F1 to F5" (PR #26) are not the
same findings as the WS3 security audit of 2026-10-29 ("audit F1 to F12",
PRs #27, #28 and #30).

---

## 2. Test evidence

Offline tests and live-model evaluation are reported separately. Offline
tests use scripted model answers (`ScriptedLLM`) and synthetic data; they
check code, not model quality. Live-model evaluation sends real requests to
a model and is the only evidence of answer quality.

### 2.1 Offline tests (no model)

**Final regression, Step 5 (2026-11-01, `main` at `052336f`).** Python
3.15.1, pytest 9.2.0, Windows 11. Details:
`docs/evidence/2026-11-01-ws3-step5-regression.md`.

| Suite | Command | Result |
|---|---|---|
| WS3 agent (`ai-agent/`) | `python -m pytest -q -rs -p no:cacheprovider` | **1036 passed, 1 skipped** (27.35 s). The skip is the opt-in live Ollama test (`RUN_OLLAMA_TESTS` unset). |
| WS1 + WS2 root (`tests/`) | `python -m pytest -q -rs -p no:cacheprovider tests/` | **53 passed** (2.54 s) |
| Live demo script | `py_compile scripts/live_team_mcp_chat.py` | compiles; not run |

- The WS3 suite includes the dataset oracle replays (ideal answers through
  the real checks, no model), among them the 37 `heldout2` oracles in
  `tests/test_heldout2.py` (40 tests with its 3 shape tests). These are not
  a `heldout2` evaluation.
- The root test `tests/test_team_mcp_http_integration.py` runs the WS3
  `BannerTools`, planner and `SchedulingAssistant` (scripted model) against
  the protected MCP server over Streamable HTTP in process, with a
  synthetic signed token: no token gives HTTP 401, another student's record
  gives `FORBIDDEN` with no backend call, and the plan returns `SEC1001`.
- Not covered by Step 5: Python 3.12/3.13 (the CI versions) and Linux. No CI
  run pinned to `052336f` is recorded here.

**Completed P1 checkpoint (2026-10-28, selected baseline `220e325`; historical).**

- 643 passed, 1 skipped in 13.31s on Python 3.14.4, Linux WSL2 aarch64.
  The skip is the opt-in Ollama test; no live model calls occurred.
- Stdio demo: `SEC1001` + `SEC2002`, 6 credits,
  `fits_current_registration`, 7 successful MCP calls.
- Stdio contract probe: 13 PASS / 3 expected FAIL; malformed scratch copy:
  7 PASS / 9 expected FAIL. Missing structured error codes and authorization
  in the fake server remain failures, not production acceptance.
- These results are supplemental. Python 3.12/3.13 CI parity, HTTP transport,
  bearer validation, real WS2/WS4 integration and network-outage behavior
  were not exercised by P1. No packages were installed.

**Historical automated evidence (2026-10-22, `4dd16f1`; same `ai-agent/` tree as `220e325`).**

- `python -m pytest -q` in `ai-agent/`: **643 passed, 1 skipped** on
  Python 3.13 and on Python 3.12 (Linux). The skipped test is the opt-in live
  model test. Before PR #14 the count was 584.
- CI on `main`: run 39804086408, **4/4 jobs succeeded** (Ubuntu and Windows,
  Python 3.12 and 3.13), 643 passed and 1 skipped in each. PR #14's own run
  (39796340703) had the same result.
- Dataset oracle replays inside pytest (ideal answers through the real checks,
  no model): development 19/19, first held-out set 34/34, security set 11/11,
  `heldout2` 37/37.

- The `ai-agent/` and `.github/` trees are identical at `4dd16f1` and
  `220e325`, so this CI evidence covers the selected baseline. No CI run
  pinned to the `220e325` SHA is separately recorded.

**Historical integration checks (2026-10-22, no model; not rerun).**

| Check | Result |
|---|---|
| Planner over stdio (`dev/demo_plan.py S10001 2027SP CIS376 CIS410`) | One option, `SEC1001` + `SEC2002`, `fits_current_registration`; 7 MCP calls (also at `4dd16f1`) |
| Contract probe over Streamable HTTP with a bearer header (fake server on `127.0.0.1`, `4dd16f1`) | 13 PASS. 3 FAIL as expected, because the fake server has no error codes (C7, C8) and no authorization (C11). |
| Contract probe against malformed data (`"active": "false"`, `"prerequisites": "CIS376"`) | Each problem named on the raw result before parsing; the agent's parsing fails with `backend_data_error`; no plan is built (checklist B4) |
| Structured `error_code` returned by a real SDK `MCPServer` tool | Read correctly; `NOT_FOUND` maps to `not_found` |
| Text-only error "auth token not found" from `get_student_record` | Reported to the model as "Student record not found." Hence contract §4.1 E2: every error must carry an `error_code`. |
| `heldout2` integrity | `cases.json` and `data/` identical to the pre-registration commit `0b4030e` |

### 2.2 Live-model evaluation

**WS3 live runs (qwen3:8b via Ollama, CPU sandbox, temperature 0).** All
were recorded on 2026-10-19, on code up to PR #9. Details are in handoff §4.

- First held-out set: **25/34 in both runs**, with 0 false or unsupported
  academic claims and 0 hard-limit violations (code before the security
  hardening).
- **Second held-out set `heldout2` (Step 6, 2026-11-01/02): 23/37 (62.2 %)
  in both runs** under scoring v2.1 and v2.2, pre-registered code
  `d4eacbf`, GitHub Actions CPU runner; 35/37 cases with the same outcome,
  1 false claim per run, 0 unsupported claims, 0 hard-limit violations, 10/11
  attacks handled, no leak of internal instructions, no infrastructure
  failure (`docs/evidence/2026-11-02-heldout2-report.md`).
- Other live results are development results.
- No live evaluation is recorded for the code of PRs #11 to #30; neither P1
  nor Step 5 ran a model.

**WS2-reported exploratory demos (2026-10-31).** WS2 reports single local
runs of `scripts/live_team_mcp_chat.py` with `qwen3:4b-instruct` and
`una-scheduler:latest` through the protected MCP server
(`docs/workstream2-mcp-integration.md`). They are WS2's observations, not a
WS3 evaluation, and were not rerun for this summary.

---

## 3. Limitations

**Functional**

- **Single turn.** There is no conversation history. A reply to a
  clarification question has no context, so the student must restate the
  request (contract §7 G3).
- **No best-subset optimization.** Course-level exclusions can leave options
  for fewer than all requested courses, with reasons in `excluded`. If all
  remaining courses cannot fit together, the planner does not search smaller
  subsets for a "best 2 of 3" (R1). Options that conflict with current
  registrations are labelled and ranked last, not removed.
- **Day-specific limits.** Limits for some days only ("Monday mornings")
  cannot be expressed; they are asked about (R3).
- **Constraint reading.** English and keyword based, and not validated on
  real student wording.
- **Prerequisites.** AND rule only, no minimum grades; only `completed`
  counts.
- **ID formats.** The mock formats are hard-coded (G4).
- **Strict data types (since PR #14).** A non-boolean `active` or
  non-array `prerequisites` / `corequisites` stops the request with a data
  error (contract §3.7). Before, `"false"` was read as active (G1) and a
  string was split into characters (G2). Data that breaks the contract now
  makes the agent unavailable for that record, not wrong. Since PR #26 the
  same holds for non-integer or negative counts, empty or non-array meeting
  `days`, and times that are not ASCII 24-hour `HH:MM`; since PR #27 for a
  record that carries another student's `student_id`.
- **Request and search limits.** A message over 4000 characters gets a
  fixed answer and is not read (PR #27). The model sees at most 20 search
  results per search (PR #25); the MCP server still returns every match.
- **Section details in answers (PR #30).** Days, times and credit hours
  given for a planned section are checked against the planner result.
  Locations, seats and modality given in an answer are not checked.
- **Error codes from WS2.** The protected server sends `FORBIDDEN`,
  `NOT_FOUND`, `INVALID_ARGUMENT`, `BACKEND_DATA` and `UNAVAILABLE`. Only
  `NOT_FOUND` has its own handling; the others become the generic
  `tool_error`, so `UNAVAILABLE` is not reported as "not reachable" (contract
  §4.1, G5).
- **Latency.** 3 to 13 minutes per request on a 2-vCPU CPU sandbox; GPU
  latency is not measured.
- **Evaluation.** Not blind: the rules and most cases were written by the
  same developer.

**Security**

- **Input inspection** is keyword based and misses about half of new-wording
  attacks.
- **Leak detection.** Paraphrased or translated prompt leaks are not
  detected.
- **Multi-turn attacks** are untested.
- **Student data in diagnostics.** `trace` and `mcp_calls` contain student
  data and need a retention policy (contract §6 W2).
- **Authorization** of MCP calls is enforced by WS2's protected server
  (PR #29, tested with a synthetic signed token only); the agent's binding
  is a second layer (contract §5 I4). No live Entra login has been tested.

---

## 4. Remaining dependencies (blocked by other workstreams or the team)

| Owner | Needed | Blocks |
|---|---|---|
| WS2 | **Delivered for synthetic data in PR #29:** the five tools plus `get_student_enrollments`, structured `error_code` on errors, per-student authorization (`FORBIDDEN`), Streamable HTTP with a bearer token. Still open: the full checklist §1 run against the protected server (C7, C8, S2, S4 to S7), real Entra configuration, and data from real Banner | Real-user end-to-end test |
| WS1 | Confirm WS2 mapping/filtering (see handoff §7), real ID formats, and the data questions in handoff §7. Endpoints for students, courses, sections, history, enrollments and terms exist in `app/main.py` at `220e325`, and the mock data already uses a JSON boolean `active` and array requirements; real Banner data must keep both (§3.7 — since PR #14 anything else stops the request) | WS2's server |
| WS4 | `student_id` from the validated Entra token (§5 I1); token on the MCP connection (§5 I5); display rules and connection-failure handling (§6 W1, W5); long-request handling (W3); logging and retention (W2); conversation state (W4) | Any real-user use |
| Team | Remove or only flag options that conflict with current registrations; partial schedules; conversation history; blind test set and human review | R1, R2, evaluation strength |

---

## 5. Unfinished items within Workstream 3's own scope

**Remaining evidence work**

| # | Item | Kind | Notes |
|---|---|---|---|
| 1 | **Step 6: done** (2026-11-01/02): `heldout2` run twice and reported | Evaluation (no code) | Pre-registered code `d4eacbf`, GitHub Actions CPU runner (`.github/workflows/heldout2-eval.yml`); 23/37 in both runs. Report: `docs/evidence/2026-11-02-heldout2-report.md`. A run of current `main` would need an explicit evaluation-code decision (audit §3.4). |
| 2 | Measure latency on the GPU | Measurement (no code) | Needed for contract §6 W3 |
| 3 | Strict parsing of `active` (JSON boolean) and of `prerequisites` / `corequisites` (arrays) in `scheduling/models.py`, with tests | Code fix (G1, G2): **done** | PR #14, merged 2026-10-22 (59 tests). G1 could fail open before; malformed values now fail closed. |

**Workstream 3 code changes at integration time** (small; blocked until the
other side decides):

| # | Item | Waiting for |
|---|---|---|
| 4 | Option in `dev/chat.py` and `evaluation/run_eval.py` to connect to WS2's server (URL, token from the environment), so the checklist §4 cases can be automated. WS2's `scripts/live_team_mcp_chat.py` covers a single manual request; the runner is still stdio only | Unblocked: WS2's transport (Streamable HTTP, bearer) is known since PR #29 |
| 5 | Align `TOOL_NAMES`, argument names and the fake server's tool names | **Done:** the protected server's six tool names and arguments match `TOOL_NAMES` (PR #29 tests) |
| 6 | Change the ID patterns (G4) | WS1 ID formats |
| 7 | Map `UNAVAILABLE`, `BACKEND_DATA`, `FORBIDDEN` and `INVALID_ARGUMENT` to their own agent codes and messages (G5) | Unblocked: WS2 published the list in PR #29; WS3 code change |
| 8 | Accept clarification answers in a follow-up turn (R2, G3) | WS4 / team decision on conversation state |
| 9 | Remove or keep conflicting options; partial schedules (R1) | Team decision |

Item 3 was fixed in PR #14 and item 5 is resolved by PR #29. Items 4 and 7
are small WS3 changes that are now unblocked; items 6, 8 and 9 depend on
other workstreams or team decisions. Items 1 and 2 remain evaluation work for
the lab. A live Entra login, real data and current model evidence remain
open before claiming a complete verified handoff.

---

## 6. Handoff notes

- **Start here.** Teams integrating with Workstream 3 should start from the
  contract and run the checklist's probe against their server first.
- **Changes to the agent.** Agent-side changes go through Workstream 3 and
  are re-checked with `python -m pytest -q` in `ai-agent/` (expect 1036
  passed, 1 skipped on `052336f`), `python -m pytest -q tests/` from the
  repository root (expect 53 passed) and checklist §0.
- **Publication rules.** Contributors follow `CLAUDE.md` and run
  `python ai-agent/dev/prepublish_check.py` before pushing or posting.
