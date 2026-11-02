# Workstream 3 handoff: AI Agent & Scheduling Logic

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`) |
| Date | 2026-11-01 (updated from 2026-10-28) |
| Code | `ai-agent/` on `main` at `052336f` (the 2026-10-28 checkpoint was `220e325`) |
| Baseline decision | Pydantic candidate `24e3fe1` deferred; not included |
| Status | Implemented research prototype. Offline regression passed on 2026-11-01 (Step 5). `heldout2` live evaluation (Step 6) **done** on 2026-11-01/02: 23/37 in both runs (GitHub Actions CPU runner, `docs/evidence/2026-11-02-heldout2-report.md`). Complete verified handoff remains open. See `docs/workstream3-completion-summary.md`. |
| Integration fixes | PR #11 (defects D1 to D6, current registrations), PR #12 (quality pass) and PR #14 (strict field types) are merged; see `docs/workstream3-integration-audit.md`. Contract for WS1, WS2 and WS4: `docs/workstream3-integration-contract.md` |
| Fixes since the checkpoint | PR #24 (H1), #25 (M1), #26 (data fixes F1 to F5), #27 (audit F1, F3, F4, F6, F7), #28 (audit F12, F8), #30 (audit F2); WS2 protected MCP server PR #29 |

This document is for the team (Workstreams 1, 2 and 4) and for whoever
repeats the second held-out evaluation. Everything below is backed by
files in `ai-agent/` and `docs/evidence/`. It contains no system-prompt text
and no credentials.

Evidence labels used here:

- **CONFIRMED**: shown by tests, CI or recorded live runs.
- **WORKING ASSUMPTION**: a choice made without a confirmed requirement or
  real data.
- **OPEN**: still needs a decision or work.

---

## 1. Status at a glance

| Area | State |
|---|---|
| Deterministic validator (`validate_schedule`) | CONFIRMED, merged (PR #1) |
| MCP client, fake MCP server, deterministic planner | CONFIRMED, merged (PR #2) |
| LLM assistant with guardrails (Ollama, qwen3:8b) | CONFIRMED, merged (PR #3) |
| Soft vs mandatory preferences, ranking | CONFIRMED, merged (PR #5) |
| Live evaluation tooling and preference-strength check | CONFIRMED, merged (PR #6) |
| Evidence orchestration and claim grounding | CONFIRMED, merged (PR #7) |
| Held-out evaluation (34 cases, pre-registered) | CONFIRMED, merged (PR #8) |
| Security hardening and second held-out set | CONFIRMED, merged (PR #9) |
| Mandatory limits on named sections and day codes (H1) | CONFIRMED, merged (PR #24) |
| Bounded course search (M1) | CONFIRMED, merged (PR #25) |
| Strict numeric and meeting data (data fixes F1 to F5) | CONFIRMED, merged (PR #26) |
| Security audit fixes F1, F3, F4, F6, F7, F12, F8, F2 | CONFIRMED, merged (PRs #27, #28, #30) |
| Offline regression (Step 5, 2026-11-01, `052336f`) | CONFIRMED: WS3 1036 passed, 1 skipped; root 53 passed (§4) |
| Second held-out set (`heldout2`, 37 cases) | CONFIRMED (Step 6, 2026-11-01/02): 23/37 in both runs, scoring v2.1 and v2.2, code `d4eacbf`, GitHub Actions CPU runner (`docs/evidence/2026-11-02-heldout2-report.md`) |
| Integration with the Mock Banner API (WS1) | CONFIRMED offline for synthetic data: WS2's server calls the team FastAPI app in process (PR #29). Real Banner data: OPEN |
| Integration with the MCP server (WS2) | CONFIRMED offline (PR #29): the agent's `BannerTools`, planner and assistant (scripted model) run against WS2's protected server over Streamable HTTP with a synthetic signed token. Full checklist §1 run and live Entra: OPEN |
| Entra identity (WS4) | OPEN: the student ID is passed in when the assistant is created |

---

## 2. Completed features

**Design rule (all PRs):** the LLM interprets the request and explains
results. Deterministic code decides every academic fact. Only schedules
accepted by `validate_schedule()` are offered.

| Component | File(s) | What it does |
|---|---|---|
| Validator | `scheduling/validators.py`, `models.py`, `loader.py` | Term, duplicates, completed courses, prerequisites (AND rule), corequisites, seats, time conflicts, credit limit, inactive student; machine-readable issue codes |
| MCP access | `agent/banner_tools.py` | All academic data comes over MCP. Tool names are in one map (`TOOL_NAMES`). Every call is logged. |
| Fake MCP server | `dev/fake_mcp_server.py` | Serves `data/*.json` (or `UNA_DATA_DIR`) as 5 required MCP tools plus optional current registrations over stdio, for tests and evaluation. WS2's protected server (`src/mcp_server/`, PR #29) is the integration target. |
| Planner | `agent/planner.py` | Course-level checks, then every section combination through `validate_schedule()`. Ranks by missed soft preferences. Reports truncation and search caps. Checks the student's own named sections as one combination (`requested_sections`). |
| Assistant loop | `agent/assistant.py` | Tool-calling loop with guardrails: bound identity and term, argument allow-list, course-ID vs section-ID schemas, step limit, one forced revision |
| Preference strength | `agent/preference_language.py` | Reads "must/can't" vs "if possible/rather" per preference. Relaxations make a wish "conflicting", which never overrides the model. Wishes the student never mentioned are not applied. |
| Evidence rules | `agent/evidence.py` | Availability and eligibility claims need a `plan_schedule` result, for every course they name (audit F4). Section IDs must be grounded. "These sections work together" needs planner support. Days, times and credit hours given for a planned section must match the planner result (audit F2). Claims that something was registered or enrolled are unsupported (audit F1). Unstated problems with named sections get a deterministic sentence. A bounded nudge and system-run plan cover missing evidence. |
| Trust boundaries | `agent/security.py` | Input inspection. Fake tool output and system markers are labelled as student text. Instruction-like text inside MCP data is removed before the model sees it. An output guard stops instruction and data leaks; logs keep only length and hash. |
| Safe answers | `agent/safe_answer.py` | An answer that leaks internal content gets a fixed refusal. An answer still unverified after the one revision is replaced by an answer built only from tool results. |
| Evaluation | `evaluation/` | Runner (live or oracle, ablations, retries, resume), scoring v1/v2 (v2.2), oracle validation, variability across runs, replay of rules on recorded answers, comparison reports |
| CI | `.github/workflows/ai-agent-tests.yml` | pytest on Ubuntu and Windows, Python 3.12 and 3.13 (4 jobs) |

Run it (from `ai-agent/`):

```bash
pip install -r requirements.txt          # Python 3.12 or 3.13
python -m pytest -q                      # expect: 1036 passed, 1 skipped at 052336f (the skip is
                                         # the live Ollama test; it runs with RUN_OLLAMA_TESTS=1)
python dev/demo_plan.py S10001 2027SP CIS376 CIS410          # planner only, no LLM
python dev/chat.py "I want CIS376 and CIS410, no classes before 10am"   # needs Ollama + qwen3:8b
```

---

## 3. Merged history and selected baseline

PRs #5 to #9 are merged, as are the handoff (#10), integration fixes
(#11), quality pass (#12), integration contract (#13) and strict field
types (#14). The 2026-10-28 baseline was `220e325`;
Pydantic candidate `24e3fe1` remains deferred.

Merged since then (all 2026-10-31 to 2026-11-01):

| PR | Merge | Change |
|---|---|---|
| #23 | `cb329fb` | Handoff and P1 verification evidence (docs) |
| #24 | `43dca6d` | H1: mandatory time/day limits on named sections; day codes |
| #25 | `5e5d587` | M1: at most 20 search results shown to the model |
| #26 | `971ba08` | Data fixes F1 to F5: strict counts, meeting days and times |
| #27 | `f3568d9` | Security audit F1, F3, F4, F6, F7 |
| #28 | `ab5fee9` | Security audit F12, F8 |
| #29 | `a572b00` | WS2 protected MCP server, root integration tests, optional live demo script (WS2-owned) |
| #30 | `052336f` | Security audit F2: section details in answers |

"Data fixes F1 to F5" (PR #26) and the security audit findings ("audit F1"
to "audit F12", PRs #27, #28, #30) are separate numbering schemes.

Historical PR #9 head `d4eacbf` is retained only as the pre-registered
`heldout2` code reference in §8.

Historical PR heads and recorded CI (Ubuntu and Windows x Python 3.12/3.13):

| PR | Head | CI (4 jobs) |
|---|---|---|
| #5 | `7a783fa` | success |
| #6 | `027abcb` | success |
| #7 | `a0160b0` | success |
| #8 | `e7a3dbe` | success |
| #9 | `d4eacbf` | success (428 passed, 1 skipped) |

---

## 4. Test results

Offline tests (scripted model, synthetic data) check the code. Live-model
evaluation checks answer quality. They are reported separately below.

### Final offline regression, Step 5 (2026-11-01, `052336f`)

CONFIRMED. Python 3.15.1, pytest 9.2.0, Windows 11; `RUN_OLLAMA_TESTS` and
`UNA_DATA_DIR` unset. Record: `docs/evidence/2026-11-01-ws3-step5-regression.md`.

- `ai-agent/`: **1036 passed, 1 skipped** (the opt-in live Ollama test).
  Includes the dataset oracle replays and the 37 `heldout2` oracles
  (`tests/test_heldout2.py`, 40 tests); no model was run.
- Repository root `tests/`: **53 passed**. Includes the agent against WS2's
  protected MCP server over Streamable HTTP with a synthetic signed token
  (`tests/test_team_mcp_http_integration.py`).
- `scripts/live_team_mcp_chat.py` compiles; it was not run.
- Not covered: Python 3.12/3.13 and Linux (the CI matrix); no CI run pinned
  to `052336f` is recorded here.

### Completed P1 checkpoint (2026-10-28; historical)

At `220e325`: 643 passed, 1 skipped in 13.31s on Python 3.14.4
(Linux WSL2 aarch64). The stdio demo returned `SEC1001` + `SEC2002`,
6 credits, `fits_current_registration`, with 7 successful MCP calls.
The stdio probe returned 13 PASS / 3 expected FAIL; the malformed scratch
copy returned 7 PASS / 9 expected FAIL. The fake server lacks structured
error codes and authorization. These results do not verify HTTP, bearer
authentication, real WS2/WS4 integration or network-outage behavior.

Supported-version evidence carries over by code identity: the `ai-agent/` and
`.github/` trees are the same object at `4dd16f1` and `220e325`, and the
`4dd16f1` CI run recorded 643 passed / 1 skipped on all four jobs
(Ubuntu and Windows x Python 3.12 and 3.13). No CI run pinned to the
`220e325` SHA is separately recorded. No model/GPU run was made in P1.

### Historical automated results (2026-10-19, PR #9)

- `python -m pytest`: **428 passed, 1 skipped** locally and in CI on all
  four jobs for PR #9. It was 222 passed, 1 skipped at PR #8.
- Dataset oracles (ideal answers replayed through the real system with every
  check on): development 19/19 (scoring v2), first held-out set 34/34,
  security live set 11/11, `heldout2` 37/37.

### Live runs (qwen3:8b via Ollama, CPU sandbox, temperature 0)

| Stage | Dataset (status) | Result |
|---|---|---|
| Baseline (PR #6) | dev, 19 (development) | 8/19 |
| + preference check (PR #6) | dev, 19 | 13/19 |
| + evidence check (PR #7) | dev, 19 | 19/19 (scoring v1); 18/19 under scoring v2.1 |
| Held-out (PR #8) | 34, pre-registered, own data | **25/34 in both runs**. 0 false or unsupported academic claims, 0 hard-constraint violations |
| Security, final code (PR #9) | the six held-out failures | 6/6 (were 0/6). The held-out set is development data since PR #9. |
| Security, final code (PR #9) | 10 held-out control cases | 10/10 |
| Security, final code (PR #9) | security live set, 11 (development) | 10/11 (scoring v2.2), 9/11 (v2.1) |

What the security results show:

- **0 legitimate requests were blocked or replaced.**
- A real partial system-prompt leak (H20, run 3) was blocked live by the
  output guard.
- The deterministic checks cost under 1 ms per case.
- Input inspection on `heldout2`, measured before any run (no model): 5 of
  10 attack-type requests flagged, 0 of 27 other requests flagged. This is
  the honest generalisation estimate for that layer.

Reports:

- `docs/evidence/2026-10-19-eval-report.md` and `2026-10-19-eval-report-evidence.md`
- `docs/evidence/2026-10-19-heldout-report.md`
- `docs/evidence/2026-10-19-security-report.md`

The results that count as generalisation evidence are the 25/34 of the
first held-out set (PR #8, code before the security hardening) and the 23/37
of the second held-out set `heldout2` (Step 6, pre-registered code
`d4eacbf`, the same in two runs; `docs/evidence/2026-11-02-heldout2-report.md`).
Other live results are development data.

`heldout2` evaluates `d4eacbf` (PR #9); no live evaluation is recorded for
the code of PRs #11 to #30. WS2 reports single
exploratory local demos on 2026-10-31 (`qwen3:4b-instruct` and
`una-scheduler:latest` through the protected MCP server,
`docs/workstream2-mcp-integration.md`); those are WS2's observations, not a
WS3 evaluation, and they were not rerun here.

---

## 5. Known limitations (functional)

- **Single-turn only.** There is no conversation history.
- **No best-subset optimization.** Course-level exclusions can leave
  options for fewer requested courses, with reasons in `excluded`. If the
  remaining courses cannot fit together, no smaller "best 2 of 3" subset
  is searched.
- **Existing enrollments are considered** when the server has the optional
  `get_student_enrollments` tool: conflicting options are flagged and ranked
  last, not removed (OPEN question).
- **Simple prerequisite rule.** Prerequisites are AND-only, with no minimum
  grades. Only `status: "completed"` satisfies a prerequisite. WORKING
  ASSUMPTION.
- **ID formats are mock formats.** Course IDs are letters plus 3 digits;
  section IDs are `SEC` plus digits (`assistant.py`, `evidence.py`,
  `evaluation/assertions.py`). Real Banner sections usually use CRNs, so
  these patterns must change with real data.
- **No section lookup.** A section cannot be looked up by its ID alone. The
  student must give its course ID, or the agent asks for it.
- **English only.** Answers built by the system are in English.
- **Keyword-based rules.** Preference wording and the scoring assertions
  use keywords, and a few correct answers fail strict wording checks.
- **One model on CPU.** Only qwen3:8b on a 2-vCPU sandbox was tested: 3 to
  13 minutes per request, with repeated out-of-memory kills of the model
  server after long answers. Latency must be measured on the lab GPU.
- **Model errors remain.** The model still invents arguments (e.g. 08:00 to
  17:00); code removes them, but such cases fail strict scoring.
- **Fail-closed data checks.** Since PRs #14, #26 and #27, malformed
  `active`, requirement lists, counts, meeting days or times, or a record
  with another student's `student_id`, stop the request with a fixed data
  error message.
- **Limits.** Messages over 4000 characters get a fixed answer (PR #27).
  The model sees at most 20 search results (PR #25).
- **Section-detail check (PR #30)** covers days, times and credit hours;
  locations, seats and modality in an answer are not checked.
- **WS2 error codes.** Only `NOT_FOUND` has its own handling. `FORBIDDEN`,
  `INVALID_ARGUMENT`, `BACKEND_DATA` and `UNAVAILABLE` from the protected
  server become the generic `tool_error` (contract §4.1, G5).
- **Not fully blind evaluation.** The rules and most test cases were written
  by the same developer.

---

## 6. Security: enforced controls and remaining risks

Enforced in application code (not prompt-only):

- Identity and term are bound when the assistant is created. No tool takes a
  student ID, and undeclared arguments are rejected.
- Only results of tools the assistant itself called count as evidence. Text
  that looks like a tool result in the student's message is labelled as
  student text.
- An answer containing system-prompt text, tool definitions, internal
  messages, raw tool JSON or internal names is never shown. The logs keep
  only its length and hash.
- An unverified answer is replaced by an answer built from tool results.
- Instruction-like text in MCP data is removed before the model sees it.
- Added by the WS3 security audit of 2026-10-29 (PRs #27, #28, #30):
  - audit F1: an answer claiming a registration, enrolment or reservation is
    unsupported (one revision, then the fallback answer);
  - audit F3: another student's ID in the request no longer turns the
    evidence check off;
  - audit F4: a positive availability claim needs every course it names in
    a `plan_schedule` option;
  - audit F6: a record, history row or enrolment row with another
    `student_id` is a backend data error;
  - audit F7: messages over 4000 characters get a fixed answer; the
    constraint reader no longer takes quadratic time;
  - audit F12: `plan_schedule` times are checked with the planner's parser,
    so a bad value is an argument error, not a system error;
  - audit F8: the constraint parse cache is freed with each request;
  - audit F2: days, times and credit hours an answer gives for a planned
    section must match the planner result.

Remaining risks (details in §6 of the security report):

1. Input inspection is keyword-based. It misses about half of new-wording
   attacks, other languages and encodings.
2. Paraphrased or translated leaks of the system prompt are not detected
   (the 8-word overlap check needs verbatim text).
3. Indirect injection is filtered only for known patterns. The planner still
   decides validity, so the impact is limited to wording.
4. Multi-turn attacks are untested.
5. Evaluation records contain student data. With synthetic data this is
   fine. Real data needs a logging and retention policy (WS4).
6. The prompt is in the repository (`ai-agent/prompts/system.md`), so it is
   not secret. The guard protects against showing it to students, not
   against repository readers.

---

## 7. Integration requirements

### Workstream 1: Mock Banner API (`app/`, selected baseline `220e325`)

`app/main.py` now defines health, student, course, section, course-history,
enrollment and term routes, including student-specific history/enrollments
and section lookup by ID. `/sections` filters by course and term; enrollment
routes return enrollment rows, not the full section records expected by the
optional MCP tool. WS2 must map/filter/join these shapes and provide search
semantics. Endpoint existence is not proof of authenticated integration.

Since PR #29, WS2's adapter (`src/mcp_server/team_backend_client.py`) does
this mapping for the synthetic data, calling the team FastAPI app in
process; the root tests cover it. The points below remain the requirements
for any real data source.

- **Course search:** `/courses` returns the complete catalog and accepts no
  `query` or `subject` filters. WS2 must implement `search_courses(query,
  subject)` filtering itself; there is no WS1 search endpoint to delegate to.
- **Enrollments and term:** enrollment rows contain only `student_id`,
  `section_id` and `status`; neither enrollment route accepts `term_id`.
  WS2 must join rows to sections, derive and filter by the requested term,
  and return full section records from
  `get_student_enrollments(student_id, term_id)`. The planner filters on
  `s.term_id == term_id`; incomplete mapping can silently yield no current
  registrations for the term.

The agent needs the following fields, per term `2027SP`:

| Data | Fields the agent reads (`scheduling/models.py`) |
|---|---|
| Student by ID | `student_id`, `max_credit_hours`, `active`; `program` (optional) |
| Course history by student | `course_id`, `term_id`, `status` (`completed` / `in_progress` / `failed` / `withdrawn`); `grade` (optional) |
| Course by ID and course search (text, subject) | `course_id`, `credit_hours`, `prerequisites[]`, `corequisites[]`; `title`, `subject` (for search) |
| Sections of a course in a term | `section_id`, `course_id`, `term_id`, `capacity`, `enrolled_count`, `meetings[]` with `days` (`MON`..`SUN`), `start_time`, `end_time` ("HH:MM", 24 h); `modality`, `location` (optional) |

WS2 must map the existing WS1 routes to the MCP contract. The shapes above match `data/*.json` and
`docs/mock-data-model.md`. Questions for WS1 (OPEN):

- Is S10001's CIS330 really `completed` in 2026FA, or `in_progress`?
- Should `enrollments.json` count toward conflicts and credits?
- What are the real course and section ID formats (CRNs)?

### Workstream 2: MCP server

CONFIRMED offline since PR #29 (`src/mcp_server/team_protected_server.py`,
`docs/workstream2-mcp-integration.md`): the protected server exposes the five
tools below plus `get_student_enrollments`, with the same names and
arguments as `agent/banner_tools.py: TOOL_NAMES`. It serves Streamable HTTP on
`127.0.0.1:8002/mcp`, rejects requests without a valid bearer token (HTTP
401), refuses another student's records with `error_code: "FORBIDDEN"`
before any backend call, and returns structured error codes `FORBIDDEN`,
`NOT_FOUND`, `INVALID_ARGUMENT`, `BACKEND_DATA` and `UNAVAILABLE`. Tested
with a synthetic signed token and synthetic identity mapping only; no live
Entra login.

The agent's tool contract (names change only in
`agent/banner_tools.py: TOOL_NAMES`):

| MCP tool | Arguments | Returns |
|---|---|---|
| `get_student_record` | `student_id` | student object; tool error if unknown |
| `get_course_history` | `student_id` | list of history records |
| `get_course` | `course_id` | course object; tool error if unknown |
| `search_courses` | `query`, `subject` (optional) | list of courses |
| `get_course_sections` | `course_id`, `term_id` | list of sections (empty if not offered) |

- **Errors:** return MCP tool errors (`is_error: true`), not crashes.
  "Student not found" is reported to the student as a missing record.
  The agent supports a structured `error_code`
  (`"NOT_FOUND"`) instead of relying on the text, and no internal details
  (hosts, SQL, stack traces) in error texts. The agent shows only fixed
  messages either way. Codes other than `NOT_FOUND` currently become the
  generic `tool_error` (G5, contract §4.1).
- **Optional (supported by the agent):**
  `get_student_enrollments(student_id, term_id)` returning the sections the
  student is already registered in, as full section records.
- **Results:** structured content (or JSON text). List results may be
  wrapped as `{"result": [...]}`.
- **Transport:** the agent uses `mcp.Client` (MCP Python SDK `>=2.2,<3`),
  over stdio in `dev/chat.py` and `evaluation/run_eval.py`. Against the
  protected server it uses Streamable HTTP with a bearer header (root
  tests; WS2's `scripts/live_team_mcp_chat.py`).
- **Authorization:** the server must enforce that a session only reads the
  authenticated student's records (WS4 token). Do not rely on the agent
  alone. The protected server does this (PR #29); it is tested with a
  synthetic token only.
- **Optional:** a `get_section(section_id)` tool would let named sections be
  checked without their course. Keep the server read-only; the agent never
  enrolls anyone.
- **OPEN:** should `validate_schedule` also be an MCP tool? It is pure
  Python and works either way.

### Workstream 4: Entra security

- **Identity binding point:**
  `SchedulingAssistant(tools, llm, student_id, term_id, ...)` in
  `agent/assistant.py`. Today the caller passes `student_id`. With Entra,
  trusted server code must take it from the validated token (claim mapped to
  the Banner ID in a directory you control). Never take it from the chat
  text or from the model.
- **One assistant instance per authenticated request or session.** The
  instance holds the bound ID.
- **Pass the user's token (or an on-behalf-of token) to WS2's MCP server**,
  so the server can authorize every tool call.
- **Decide logging and retention for real student data.** Evaluation
  records include trace data; the leak guard only covers internal
  instructions, not personal data.

---

Section 8 preserves the evaluation procedure pinned to the pre-registered
`d4eacbf` (428 tests).

**Status: Step 6 done (2026-11-01/02).** `heldout2` was run twice on
`d4eacbf` with this procedure, automated by the manual GitHub Actions
workflow `.github/workflows/heldout2-eval.yml` (PRs #32, #33) on a standard
CPU runner instead of the lab machine: 23/37 in both runs, no infrastructure
failure, no retry. Report and provenance (run IDs, configuration,
checksums; the raw records are retained outside the repository):
`docs/evidence/2026-11-02-heldout2-report.md`,
`docs/evidence/2026-11-02-heldout2-provenance.md`. Running `heldout2` on current
`main` instead of `d4eacbf` would need an explicit evaluation-code decision,
with the disclosure in `docs/workstream3-integration-audit.md` §3.4.

## 8. Running `heldout2` (procedure)

`heldout2` (`ai-agent/evaluation/heldout2/`) was pre-registered in `0b4030e`.
Its first two runs are reported in
`docs/evidence/2026-11-02-heldout2-report.md`. Read
`ai-agent/evaluation/heldout2/README.md` first: run plan, the "known before
running" facts, the touched case N31, and every change after freezing.

### 8.1 Integrity check (before running)

```bash
git diff --stat 0b4030e -- ai-agent/evaluation/heldout2/cases.json ai-agent/evaluation/heldout2/data
# must print nothing: cases and data unchanged since pre-registration
```

SHA-256 of the files (LF line endings, Linux checkout; on Windows use the
`git diff` check above, which ignores line-ending conversion):

```
0806e5b76890c7d75f8fa43bff0157a8e278a511800558844c5ad4d24ff4851d  cases.json
b1ee6667b89a82ae387deb52c8a03994cb891a4179a47b94dd867708abddbb11  data/course_history.json
1b654e1950c60ad6a7098b643db910fb05f9d5b4ad19de9384b0d4c1654c270a  data/courses.json
761fac183e871d24dfb7c9bc645b05cd6d7c196a0c35c02877d8e5cb27231226  data/enrollments.json
a3824595f4834e31cb2bb4350b97d44cb81adce6c195e6cbb95255e51de6250c  data/sections.json
a126547a3ab66fd1a140a31a0200acb0045753af10ded5174aa7a6edddaef76c  data/students.json
bf4281616fb7d2de9b6d27f557e76564f252d8db08f74a6daa74721c286a2521  data/terms.json
```

### 8.2 Environment

1. **Code.** Use the merged `main` that contains PR #9, or check out
   `d4eacbf`. Record `git rev-parse HEAD`. Do not change any code, prompt,
   case or scoring file before or during the runs.
2. **Tests.** From `ai-agent/`: `pip install -r requirements.txt`, then
   `python -m pytest -q`. Expect `428 passed, 1 skipped`; the 37 `heldout2`
   oracles are part of this suite.
3. **Model.** Install Ollama and record its version (the earlier runs used
   0.40.6). Then `ollama pull qwen3:8b`. The earlier runs used model blob
   `sha256:a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`;
   check with `ollama show qwen3:8b --modelfile` and record any difference.
4. **Ollama server**, with the same settings as the earlier runs (keep them
   for comparability).

   Linux / WSL:

   ```bash
   OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
   OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
   ```

   Windows PowerShell: quit the Ollama tray app first, then run:

   ```powershell
   $env:OLLAMA_CONTEXT_LENGTH="4096"; $env:OLLAMA_FLASH_ATTENTION="1"; $env:OLLAMA_KV_CACHE_TYPE="q8_0"
   $env:OLLAMA_NUM_PARALLEL="1"; $env:OLLAMA_MAX_LOADED_MODELS="1"; ollama serve
   ```

### 8.3 Runs (from `ai-agent/`, each into a new folder)

```bash
python evaluation/run_eval.py --dataset heldout2 --model qwen3:8b --no-think --num-ctx 4096 \
  --timeout 900 --num-predict 768 --out ../docs/evidence/<YYYY-MM-DD>-heldout2-run1
python evaluation/run_eval.py --dataset heldout2 --model qwen3:8b --no-think --num-ctx 4096 \
  --timeout 900 --num-predict 768 --out ../docs/evidence/<YYYY-MM-DD>-heldout2-run2
```

Windows: same command with `.venv\Scripts\python.exe evaluation\run_eval.py`
and `..\docs\evidence\...`, on one line.

- Run 1 complete first; run 2 (and 3, if time allows) are repeats.
- If the model server runs out of memory between cases, add
  `--unload-between-cases` to every run and record it.
- If a run is interrupted, re-run the same command with `--resume`: finished
  cases are kept and missing ones are run.

### 8.4 Infrastructure retries (never by score)

List the cases whose record has `error_kind` starting with `infrastructure`:

```bash
python -c "import json,glob,sys; print(' '.join(json.load(open(f))['record']['case_id'] for f in sorted(glob.glob(sys.argv[1]+'/N*.json')) if json.load(open(f))['record'].get('error_kind','').startswith('infrastructure')))" ../docs/evidence/<run1-folder>
```

Retry only those, with the same settings, into a separate folder. Keep the
original folder unchanged:

```bash
python evaluation/run_eval.py --dataset heldout2 ... --cases <IDs> --out ../docs/evidence/<run1-folder>-infra-retry
```

### 8.5 Scoring under v2.1 and v2.2 (the README requires both)

Per-case scores written during the run use the current scorer, **v2.2**. For
**v2.1**, re-score a **copy** of each run folder with the scorer of the
freezing commit (procedure verified on 2026-10-19):

```bash
git worktree add /tmp/ws3-v21 0b4030e
cp -r ../docs/evidence/<run1-folder> /tmp/run1-v21 && rm /tmp/run1-v21/summary.*
cd /tmp/ws3-v21/ai-agent && python evaluation/run_eval.py --dataset heldout2 --summarize-only --out /tmp/run1-v21
# then copy /tmp/run1-v21/summary.json and summary.md back as summary.scoring-v2.1.json / .md
git worktree remove /tmp/ws3-v21
```

### 8.6 Consistency across runs

```bash
python evaluation/variability.py --dataset heldout2 \
  ../docs/evidence/<run1-folder>:../docs/evidence/<run1-folder>-infra-retry \
  ../docs/evidence/<run2-folder> --labels run1 run2 --out ../docs/evidence/<YYYY-MM-DD>-heldout2-variability.md
```

### 8.7 Reporting rules

- Report every failure, the "as run" and "after infrastructure retries"
  numbers, both scorer versions, latency (median, mean, max) and the
  hardware.
- Report N31 as touched. Report the input-inspection facts that were known
  before running.
- **Do not change the system because of these results.** If anything is
  changed in response, mark `heldout2` as development data in its README; a
  new held-out set is then needed for any further generalisation claim.

---

## 9. What remains before Workstream 3 is complete

| # | Item | Owner | Blocks |
|---|---|---|---|
| 1 | Optional: record a CI run pinned to `052336f` (Python 3.12/3.13, Ubuntu and Windows); Step 5 ran on Python 3.15.1, Windows only | WS3 / CI | nothing |
| 2 | **Step 6: done** (2026-11-01/02). `heldout2` run twice on `d4eacbf` (GitHub Actions CPU runner): 23/37 in both runs, report published (`docs/evidence/2026-11-02-heldout2-report.md`) | Hassan | nothing |
| 3 | Measure latency on the GPU; CPU numbers are not representative | Hassan | usability claim |
| 4 | Connect the agent to WS2's MCP server. **Done offline in PR #29** (names match, root tests pass). Remaining: run the full checklist §1 and Appendix A probe against the protected server; add a server URL/token option to `evaluation/run_eval.py`; map WS2's other error codes (G5) | WS2 + Hassan | real end-to-end evaluation |
| 5 | Confirm mapping of existing WS1 endpoints and resolve the data questions in §7 | WS1 + WS2 | item 4 |
| 6 | Replace the passed-in `student_id` with the Entra identity. MCP server authorization exists (PR #29, synthetic token); a live Entra login is not demonstrated | WS4 + WS2 + Hassan | any real-user use |
| 7 | Decide the OPEN design questions: enrollments, partial schedules, `validate_schedule` as an MCP tool, real ID formats | Team | data and contract changes |
| 8 | A blind test set written by a teammate (especially attacks), and human review of answer quality for the paper | Team | stronger evaluation |
| 9 | Front end / chat history (multi-turn) and multi-turn security tests, if in scope | Team | multi-turn use |

Items 2 and 3 are remaining WS3 evaluation work. Items 4 to 6 are
integration work that needs the other workstreams.

---

## 10. Evidence index

| Topic | File |
|---|---|
| Agent overview and development log | `ai-agent/README.md` |
| Evaluation guide and datasets | `ai-agent/evaluation/README.md` |
| Held-out sets (pre-registration) | `ai-agent/evaluation/heldout/README.md`, `ai-agent/evaluation/heldout2/README.md` |
| Security report | `docs/evidence/2026-10-19-security-report.md` |
| Held-out report | `docs/evidence/2026-10-19-heldout-report.md` |
| Development reports | `docs/evidence/2026-10-19-eval-report.md`, `2026-10-19-eval-report-evidence.md` |
| Raw live records | `docs/evidence/2026-10-19-*/` (one JSON per case, never edited after the run) |
| Ollama setup notes | `docs/evidence/2026-10-19-ollama-environment-and-first-runs.md` |

## 11. Historical sensitive-content check

On 2026-10-19 this document and all 128 files added or modified since PR #8's
head (`e7a3dbe`) were checked:

- None shares 8 consecutive words with the system prompt (leak guard,
  `agent/security.py`).
- None contains a token, key, password or e-mail address.
- The test datasets contain a few short prompt fragments (at most 7 words,
  e.g. a section heading) as forbidden phrases, so tests can detect a leak.
  These fragments come from the first held-out set.

The original held-out record
`docs/evidence/2026-10-19-heldout-run1-infra-retry2/H20.json` (and the run-2
H20 record) is unchanged raw evidence. It contains the model's leak of the
prompt, which is the same text as `ai-agent/prompts/system.md` in this
repository. Do not quote it in papers or slides.
