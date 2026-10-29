# Workstream 3 completion and handoff summary

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`), Workstream 3 (AI Agent & Scheduling Logic) |
| Date | 2026-10-28, baseline `220e325` |
| Code | `ai-agent/` at selected main baseline `220e325`; Pydantic candidate `24e3fe1` deferred |
| PRs | #1, #2, #3, #5 to #14 (excluding #4), all merged (2026-10-17 to 2026-10-22) |
| Status | **Implemented WS3 prototype; verified handoff remains incomplete.** WS1 endpoints exist in the selected baseline. Real WS2 MCP integration and WS4 identity/authorization remain unverified, as does current GPU/model evidence. Not production-ready. |

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

---

## 2. Test evidence

**Completed P1 checkpoint (2026-10-28, selected baseline `220e325`).**

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

**Live model runs (qwen3:8b via Ollama, CPU sandbox, temperature 0).** All
were recorded on 2026-10-19, on code up to PR #9. Details are in handoff §4.

- First held-out set: **25/34 in both runs**, with 0 false or unsupported
  academic claims and 0 hard-limit violations. This is the only
  generalisation evidence so far.
- Later live results are development results.
- No live run on PRs #11, #12 and #14 is recorded in this evidence; P1 added no live run on `220e325`.

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
  makes the agent unavailable for that record, not wrong.
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
- **Authorization** of MCP calls must be enforced by WS2; the agent's binding
  is a second layer (contract §5 I4).

---

## 4. Remaining dependencies (blocked by other workstreams or the team)

| Owner | Needed | Blocks |
|---|---|---|
| WS2 | MCP server with the five tools (contract §3), passing JSON types through unchanged (§3.7); `error_code` on every error (§4.1); optional `get_student_enrollments`; per-call authorization against the token (§5 I4); transport and auth method | Any end-to-end test |
| WS1 | Confirm WS2 mapping/filtering (see handoff §7), real ID formats, and the data questions in handoff §7. Endpoints for students, courses, sections, history, enrollments and terms exist in `app/main.py` at `220e325`, and the mock data already uses a JSON boolean `active` and array requirements; real Banner data must keep both (§3.7 — since PR #14 anything else stops the request) | WS2's server |
| WS4 | `student_id` from the validated Entra token (§5 I1); token on the MCP connection (§5 I5); display rules and connection-failure handling (§6 W1, W5); long-request handling (W3); logging and retention (W2); conversation state (W4) | Any real-user use |
| Team | Remove or only flag options that conflict with current registrations; partial schedules; conversation history; blind test set and human review | R1, R2, evaluation strength |

---

## 5. Unfinished items within Workstream 3's own scope

**Remaining evidence work**

| # | Item | Kind | Notes |
|---|---|---|---|
| 1 | Run `heldout2` once on the lab GPU and publish the report | Evaluation (no code) | Handoff §8. Choose the code first. PR #9's `d4eacbf` (428 tests) is the pre-registered, clean run. Selected baseline `220e325` (643 tests in P1) is an alternative only after an explicit evaluation-code decision; the disclosure in audit §3.4 then applies. |
| 2 | Measure latency on the GPU | Measurement (no code) | Needed for contract §6 W3 |
| 3 | Strict parsing of `active` (JSON boolean) and of `prerequisites` / `corequisites` (arrays) in `scheduling/models.py`, with tests | Code fix (G1, G2): **done** | PR #14, merged 2026-10-22 (59 tests). G1 could fail open before; malformed values now fail closed. |

**Workstream 3 code changes at integration time** (small; blocked until the
other side decides):

| # | Item | Waiting for |
|---|---|---|
| 4 | Option in `dev/chat.py` and `evaluation/run_eval.py` to connect to WS2's server (URL, token from the environment), so the checklist §4 cases can be automated | WS2 transport and auth method |
| 5 | Align `TOOL_NAMES`, argument names and the fake server's tool names | WS2 tool names |
| 6 | Change the ID patterns (G4) | WS1 ID formats |
| 7 | Map more error codes to their own messages, if needed (G5) | WS2 error code list |
| 8 | Accept clarification answers in a follow-up turn (R2, G3) | WS4 / team decision on conversation state |
| 9 | Remove or keep conflicting options; partial schedules (R1) | Team decision |

Item 3 was fixed in
PR #14; items 4 to 9 depend on integration contracts or team decisions.
Items 1 and 2 remain evaluation work. Real authenticated integration and
current model evidence remain open before claiming a complete verified handoff.

---

## 6. Handoff notes

- **Start here.** Teams integrating with Workstream 3 should start from the
  contract and run the checklist's probe against their server first.
- **Changes to the agent.** Agent-side changes go through Workstream 3 and
  are re-checked with `python -m pytest -q` (expect 643 passed, 1 skipped on
  `4dd16f1`) and checklist §0.
- **Publication rules.** Contributors follow `CLAUDE.md` and run
  `python ai-agent/dev/prepublish_check.py` before pushing or posting.
