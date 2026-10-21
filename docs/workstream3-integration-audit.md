# Workstream 3 integration-readiness audit

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`) |
| Date | 2026-10-19 |
| Audited code | PR #10 head `abc9cc9` (= PR #9 code `d4eacbf` + handoff docs) |
| Fixes | branch `fix/integration-readiness` on the fork, PR #11 (CI passed) |
| Quality pass | branch `fix/ws3-quality-pass` on the fork, on top of PR #11 (no pull request yet): current-registration labels, stricter constraint reading, R7 and R9 fixed (§10) |
| Verdict | **Not integration-ready.** Workstream 3's own defects D1 to D6 are fixed and tested. Integration is blocked by work outside Workstream 3 (§6). Nothing here was tested against a real Workstream 1, 2 or 4 component, because none exists yet. |

How the audit was done: code and test review of `ai-agent/`, the handoff
document and the PR chain, plus small probe scripts against the fake MCP
server (malformed data, failing tools, concurrent requests, injected
errors). No model was run: every check used scripted model replies, so no
claim here depends on qwen3:8b behaviour. `heldout2` was not run or changed.

Labels: CONFIRMED = shown by a test or probe; WORKING ASSUMPTION = chosen
by Workstream 3 and still needs confirmation; OPEN = needs a team decision.

---

## 1. Summary

| ID | Finding | Severity | Status |
|---|---|---|---|
| D1 | Backend error text (hosts, credentials, SQL) reached the model, the student and the logs | High (privacy and security) | FIXED |
| D2 | Any unexpected exception (MCP outage, malformed data, model server) crashed the run | High (availability) | FIXED |
| D3 | The fallback answer repeated the text of a failed tool call to the student | High (privacy) | FIXED |
| D4 | Hard time and day limits depended on the model filling in the arguments | High (correctness) | FIXED, with limits (§3.4) |
| D5 | Per-request state was stored on the shared assistant object | High (isolation) | FIXED |
| D6 | The MCP trace of a result contained other requests' calls | Medium (privacy in logs) | FIXED |
| E1 | Existing enrollments were never read | High (correctness) | FIXED in Workstream 3 code; needs a WS2 tool and a team decision (§3.7) |
| Q1 | Options needing a change to current registrations could still be presented as fine | High (correctness) | FIXED in the quality pass (§10.1) |
| Q2 | Constraint reading lost or misread limits in mixed, exception and unusual time wording | High (correctness) | FIXED in the quality pass (§10.2) |
| R1 to R9 | Remaining gaps | Mixed | OPEN (§5); R7 and R9 FIXED in the quality pass (§10.3) |

Tests: 428 passed, 1 skipped before; **478 passed, 1 skipped** after
(Python 3.13 and 3.12, Linux; CI on PR #11: the same on Ubuntu and Windows).
After the quality pass: **584 passed, 1 skipped** (§10.4). The skipped test
is the opt-in live Ollama test.

---

## 2. What was already ready (CONFIRMED)

- **Deterministic validity.** Every option comes from `plan_schedules()`,
  which only returns combinations `validate_schedule()` accepts. The model
  never decides validity.
- **Identity binding.** `student_id` and `term_id` are fixed when
  `SchedulingAssistant` is created. No tool takes a student ID. A student ID
  claimed in the chat is ignored, and a forged `student_id` argument is
  rejected before anything reaches MCP (`tests/test_assistant.py`,
  `tests/test_fallback.py`).
- **Argument and ID schemas, grounding, evidence rules, security layers.**
  As described in the handoff (§2 and §6 of
  `docs/workstream3-handoff.md`).
- **Partial results when one course fails.** An ineligible or unknown course
  is excluded with a reason and the other courses are still planned.
- **Sensitive content in the repository.** No tokens, keys or passwords were
  found. Exactly two tracked files share 8 consecutive words with the system
  prompt: the original H20 records
  (`docs/evidence/2026-10-19-heldout-run1-infra-retry2/H20.json`,
  `docs/evidence/2026-10-19-heldout-run2/H20.json`). They are raw evaluation
  evidence and stay unchanged by rule (see R8).

---

## 3. Defects fixed on `fix/integration-readiness`

### 3.1 D1: backend error text leaked

**Problem.** `BannerTools` raised `ToolCallError(text)` with the server's
error text, and `assistant._run_tool` returned `{"error": str(e)}` to the
model. Any text the server put in an error (a connection string, a host
name, an SQL statement, a stack trace) went to the model, could be repeated
to the student, and was written to evaluation records. Transport failures
and malformed data were not caught at all (D2).

**Fix** (`agent/banner_tools.py`).
- Every backend failure is a `BackendError` whose `str()` is a fixed, safe
  message:

  | Class | When | `code` | Message |
  |---|---|---|---|
  | `ToolCallError` | tool returned `is_error` | `not_found` / `unknown_tool` / `tool_error` | e.g. "Student record not found.", "Course not found in the catalog." |
  | `BackendUnavailable` | the call itself failed (connection, timeout, protocol) | `backend_unavailable` | "The registration system is not reachable right now." |
  | `BackendDataError` | the answer has the wrong shape (missing field, `"Mon"`, `"9:30 AM"`, non-JSON text) | `backend_data_error` | "The registration system returned data in an unexpected format." |

- The raw text is kept only in `.internal`. Logs get `log_record()`: code,
  tool, SHA-256 prefix and length of the text, so an operator can match it
  with server logs without the text being stored.
- The model receives `{"error": <fixed message>, "error_code": <code>}`.
- "Not found" is recognised from a structured `error_code` if the server
  sends one, otherwise from the text (WORKING ASSUMPTION, see §6).
- An outage while looking up a course is no longer reported as "this course
  does not exist" (`planner.py` re-raises anything that is not `not_found`).

**Tests** (`tests/test_integration_readiness.py`): error text kept out and
only hashed; not-found vs unknown-tool vs other errors; structured error code;
connection failure and bad data; for each failure type, the secret appears
neither in what the model saw, nor in the result, nor in the answer.

### 3.2 D2: unhandled failures

**Problem.** An exception anywhere in the loop (MCP outage, malformed record,
model server down, a bug) propagated to the caller. A web front end would
show an error page or a stack trace.

**Fix** (`agent/assistant.py`). `run()` catches every `Exception` (task
cancellation still propagates) and returns:
- a fixed answer ("Sorry, something went wrong on our side ..." or, for an
  unreachable backend, "The registration system isn't reachable right
  now ..."),
- `stopped_reason="error"`, `answer_source="system_error"`,
- `error = {"kind", "type", "phase", "fingerprint"}`; kinds are
  `llm_timeout`, `llm_unreachable`, `llm_server_error`, `llm_error`,
  `backend_unavailable`, `backend_data_error`, `backend_error`,
  `internal_error`. The exception text is never stored.

Wrong argument types from the model (a string where a list is expected, a
missing `course_ids`) now get a specific or generic message instead of a
Python `TypeError` text that named internal functions.

`evaluation/run_eval.py` marks such records with `error` and maps the kind
to the existing `error_kind` values (`infrastructure:timeout`,
`infrastructure:model_server`, new `infrastructure:backend`), so the
retry-by-error-kind procedure in the handoff (§8.4) keeps working.

**Tests:** model server unreachable (host name and secret absent from the
whole result), unexpected planner exception, wrong argument types,
evaluation record keeps only the category.

### 3.3 D3: fallback answer repeated tool error text

**Problem.** `safe_answer.build()` contained
`"I couldn't complete the registration check: {err}"`, filtered only by a
keyword list.

**Fix.** The fallback answer now chooses a fixed sentence from the error
code: student record not found, registration system not reachable, or a
general registration-system problem. An argument error (the model's mistake)
gives the general "I couldn't verify an answer" text. Error text is never
used.

**Tests:** one per error code, plus the argument-error case.

### 3.4 D4: hard constraints depended on the model

**Problem.** The model fills in `earliest_start`, `latest_end`,
`avoid_days` and `required_preferences`. Code only checked HOW STRONGLY a
preference was stated, and only for preferences the model passed. So:
- a constraint the model left out ("I can't do Fridays", no `avoid_days`)
  was never applied, and options with Friday classes came back as valid;
- a wrong value ("done by 6pm" passed as `20:00`) was applied as given;
- wording that `preference_language.py` does not link to a preference
  ("between 10am and 3pm", "nothing after 5", "before noon") made
  `unmentioned()` drop even the model's correct values.

**Fix** (new `agent/constraints.py`, used by `assistant._plan_schedule`).
The student's own words are read by code, independently of the model:

| Reading | What happens |
|---|---|
| mandatory and read reliably | the student's value is applied as mandatory, also when the model left it out or got it wrong |
| mandatory but not readable | no schedule is built; the student gets a fixed clarification question (`answer_source="system_clarification"`) |
| not mandatory, read reliably | the student's value replaces a different or missing model value; strength stays the model's. If the model left it out: mandatory when nothing in the student's words softens it ("No Friday classes."), soft otherwise ("ideally no Friday classes") |
| not mandatory, not readable | the model's value stands |

Every change is listed in the tool result (`constraint_changes`).
Strength comes from the same cues and lending rules as
`preference_language.py` (refactored into `fragments()`; `classify()` gives
identical results on all 1,812 test strings in the repository).

Read reliably, for example: "nothing before 10am", "start after 9:30",
"not before noon", "I'm not free until 11", "done by 3pm", "nothing after 5",
"no later than 2", "my shift starts at 1pm" (end limit), "between 10am and
3pm", "I can't do Fridays", "keep Fridays free", "I work Tuesdays", "no
weekends", "Mondays and Wednesdays only" (every other day avoided).

Not guessed (unclear, so a mandatory one is asked about): vague words without
a time ("mornings"); an hour that could be AM or PM ("after 10"); a time not
clearly a start or an end ("I can't stay until 5"); a limit for some days
only ("Monday mornings", "Fridays after 3pm"), which `plan_schedule` cannot
express; busy time ranges ("I work from 8 to 10"); day ranges ("Monday to
Thursday"); a day with no direction.

Several limits for one preference: the strictest is used ("my shift starts
at 1pm, so done by 12:30" gives 12:30).

Times without AM/PM (WORKING ASSUMPTION, classes between about 08:00 and
21:00): 13 to 23 are 24-hour times and 12 is noon; for a start, 7 to 11 are
AM and 1 to 6 are PM; for an end, 1 to 9 are PM; an end at 10 or 11 is
ambiguous.

The clarification question repeats nothing from the student's message except
an hour number.

The evidence-check recovery (the system running `plan_schedule` itself when
the model will not) used to be skipped whenever the request mentioned a time
or day. It now runs when every stated limit is read reliably, with those
limits; if a mandatory one is unclear, the student is asked.

Check against the datasets: 26 requests in the dev, held-out, `heldout2`
and security sets mention times or days. For 25, the code's reading equals
the case's expected (or oracle) values; one of them differs only in day
order. For 1 (`heldout2` N09, "No classes before 10 for me. Well, 9:30 would
be OK ..."), the reading is "not reliable", so the model's value is kept.
None triggers a clarification.

**Disclosure (`heldout2`).** While building `constraints.py`, the request
texts of all datasets were read to check the rules, including the 37
`heldout2` requests (no model was run, no file was changed). Two generic
rules were added after seeing `heldout2` wording: "keep ... clear" counts as
keeping a day free, and "if it's the only way" counts as a relaxation. The
handoff pins the `heldout2` run to PR #9's code (`d4eacbf`), which does not
contain this module, so that run is not affected. If `heldout2` is ever run
on code that contains this branch, these two rules must be reported as
"known before running".

**Limits (OPEN / WORKING ASSUMPTION).** English only and keyword based.
Strength is per preference, not per day ("Tuesdays are fine, but no Mondays
at all" is "conflicting", so Monday is not forced mandatory). A sentence
ending at "a.m." is split by the sentence rule. Not validated on real
student wording.

**Tests:** 11 reading cases, 6 unclear cases, the no-echo rule, and
assistant-level tests: omitted mandatory day enforced, wrong value replaced,
range no longer dropped, clarification instead of a schedule (no MCP call),
omitted soft wish added as soft, omitted unsoftened limit made mandatory,
the model's reading of an unsoftened limit kept, ablation switch
(`check_constraints=False`), fallback with a mandatory limit, fallback asks
instead of guessing.

### 3.5 D5: shared per-request state

**Problem.** `run()` stored the request text in `self._request`, and
`_plan_schedule` read it later. Two requests on one assistant object (for
example two browser tabs of one student) overwrote each other: in the probe,
request A ("I can't do Fridays at all") was planned with request B's text, so
A's mandatory Friday limit was dropped as "not mentioned".

**Fix.** Everything about one request lives in a `_Run` object created in
`run()` and passed explicitly (request, trace, security record, MCP calls,
step, phase). Nothing request-specific is stored on the assistant.

### 3.6 D6: mixed MCP traces

**Problem.** `AssistantResult.mcp_calls` was `list(self.tools.calls)`: the
connection-wide list. With one MCP session shared by several assistants
(several students) or several requests, every result contained the other
requests' calls, including other students' IDs.

**Fix.** `BannerTools.run_log()` collects the calls of one request in a
context variable; each result gets only its own calls. `BannerTools.calls`
stays as the connection owner's audit list.

**Tests for D5 and D6** (simultaneous requests with different identities and
constraints):
- one assistant, two concurrent requests with different limits, the first
  delayed so the second runs completely in between: each keeps its own
  limits, its options equal a solo run, and the two traces split the
  session's calls exactly;
- one MCP session, 12 concurrent requests from 3 students (S20002, S10001,
  S10002) with different constraints and staggered timing: each result has
  only its own student's calls, the same applied preferences, options and
  current registrations as a solo run, and no other student's ID anywhere in
  it.

Both tests were also run against the pre-fix code (`abc9cc9`): both FAIL
there (A lost its Friday limit; traces contained other students' calls).

### 3.7 E1: existing enrollments were ignored

**Problem.** `data/enrollments.json` (and the same file in every evaluation
data set) was never read. A student already registered in a section got
options that overlap it, repeat the same course, or exceed the credit limit
together with it, and was not told. In the development data S10001 is
registered in SEC1001 (CIS376, MON/WED 09:30-10:45); asked for CIS410, the
agent offered SEC2001 (MON/WED 10:30-11:45), which overlaps it.

**Fix (Workstream 3 side, no change to another team's code).**
- `BannerTools.enrollments()` calls an **optional** MCP tool
  `get_student_enrollments(student_id, term_id)` (proposed; the fake server
  implements it by joining `enrollments.json` with `sections.json`). If the
  tool does not exist or fails, the result is "could not check", never an
  empty list.
- The planner checks each valid option against the current registrations:
  repeated course, time overlap, credit hours including current classes.
  Options are **flagged and ranked last, not removed**
  (`current_registration`, `compatible_with_current_registration`), because
  whether they should be removed depends on what an enrollment means in
  WS1's data (OPEN). Named sections that overlap a current class get the
  issue `CONFLICTS_WITH_CURRENT_REGISTRATION`.
- The answer gets fixed notes: already registered for a course, which options
  overlap which current class (course and time, no current section ID), the
  credit limit, or "I couldn't check the classes you're already registered
  for" when the backend cannot list them.

**Impact on existing results.** Options are not removed, so planner outcomes
and all dataset oracles are unchanged. Answers for S10001 and S10002 now
carry these notes when the plan touches their registrations. Until WS2
provides the tool, every planned answer will say registrations could not be
checked; that is intended.

**Tests:** overlap flagged, ranked last and told; already-registered course
told; tool missing reported and nothing removed; credit limit with current
classes flagged (planner stub).

---

## 4. Test results

| Run | Result |
|---|---|
| Before (`abc9cc9`), Python 3.13 | 428 passed, 1 skipped |
| After, Python 3.13 | **478 passed, 1 skipped** |
| After, Python 3.12 (fresh virtual environment from `requirements.txt`) | **478 passed, 1 skipped** |
| Concurrency tests against pre-fix code | 2 of 2 fail (expected; shows they detect D5 and D6) |

- New: `tests/test_integration_readiness.py` (47 tests) and three tests in
  `tests/test_evidence.py` / `tests/test_fallback.py`.
- Changed, because behaviour changed on purpose (3 tests):
  - the system-run plan now applies a reliably read time limit instead of
    not running (the "not run" tests now use wording code cannot read);
  - the ablation test for unverified answers now expects the registration
    note after the model's unchanged answer.
- The dataset oracle replays (dev, held-out, security and the 37 `heldout2`
  oracles, all scripted, no model) pass unchanged.
- CI (GitHub Actions does not run on the fork) ran when PR #11 was opened,
  on its head `5a598d5`: all four jobs passed (Ubuntu and Windows, Python
  3.12 and 3.13), each with 478 passed, 1 skipped.

---

## 5. Remaining defects and gaps (not fixed here)

| ID | Gap | Why not fixed |
|---|---|---|
| R1 | **No partial schedule when all combinations fail.** If every combination of the requested courses fails (e.g. a time conflict under mandatory limits), the result is only rejection counts; no "best 2 of 3". CONFIRMED by probe. | A new feature; needs a team decision on what to offer |
| R2 | **Single-turn only.** Each `run()` starts a new conversation, so a follow-up ("what about Fridays?") or an answer to a clarification question has no context. | Needs a decision with WS4 on where conversation state lives |
| R3 | **Time limits apply to every day.** The planner has one earliest start and one latest end; "Monday mornings" cannot be expressed (now asked about, not guessed). | Planner model change; scope decision |
| R4 | **Constraint reading is English, keyword based.** See §3.4 limits. | Needs real student wording to improve |
| R5 | **"Not found" is recognised from error text** unless the server sends a structured `error_code`. | Needs the WS2 contract (§6) |
| R6 | **Mock ID formats** (`SEC` + digits, letters + 3 digits) are hard-coded in several places. | Needs WS1's real formats (CRNs) |
| R7 | **`dev/chat.py` does not pass `UNA_DATA_DIR`** to the stdio server (the MCP SDK passes only a few safe environment variables), so it always uses `data/`. `run_eval.py` passes it explicitly. | FIXED in the quality pass (§10.3) |
| R8 | **Two original H20 records contain prompt text** (the model's real leak in that run). | Raw evidence must stay unchanged; the prompt is in the repository anyway |
| R9 | **`OllamaLLM.stats` is per LLM object**, so concurrent requests sharing one object mix their timing statistics. | FIXED in the quality pass (§10.3) |

Security risks from the handoff (§6) still apply: keyword input inspection,
paraphrased leaks not detected, multi-turn attacks untested, logging and
retention of real student data undecided.

---

## 6. Integration blockers by owner

| Owner | Needed | Blocks |
|---|---|---|
| Workstream 2 (MCP server) | Real server with the five tools (names in `TOOL_NAMES`); **structured error codes** (`error_code: "NOT_FOUND"` with `is_error`), and error texts without internal details; the optional `get_student_enrollments(student_id, term_id)` returning full section records; authorization of every call against the authenticated student | any end-to-end test |
| Workstream 1 (Mock Banner API) | Endpoints for courses, course history, sections; enrollments with **term and status**; the data questions in handoff §7 | WS2 server |
| Workstream 4 (Entra) | `student_id` from the validated token at `SchedulingAssistant(...)` creation; one assistant per authenticated session or request; showing `system_clarification` and `system_error` answers; logging and retention policy for traces (they hold student data; the `security.backend_errors` entries hold only hashes) | any real-user use |
| Team | Remove or only flag options that conflict with current registrations? Partial schedules? Conversation history? Real ID formats? | E1, R1, R2, R6 |

**The system must not be called integration-ready until the WS2 server, the
WS1 data and the WS4 identity binding exist and an end-to-end test against
them passes.**

---

## 7. End-to-end demonstration plan

Today (fake MCP server, no other workstream needed):

1. `python -m pytest -q` from `ai-agent/` (expect 584 passed, 1 skipped on
   the quality-pass branch; 478 on PR #11).
2. `python dev/demo_plan.py S10001 2027SP CIS410` (planner over stdio MCP, no
   model): SEC2002 fits, SEC2001 needs a change (it overlaps S10001's current
   CIS376 class). Add `--data-dir <folder>` to use other data.
3. With Ollama: `python dev/chat.py "I can't do Fridays at all. Plan CIS410."`
   then `python dev/chat.py "I can't do mornings. Plan CIS410."` (expect a
   clarification question, no schedule).
4. Show the guardrail tests: a forged student ID, a backend outage and a
   malformed record, and the concurrency tests.

After integration (acceptance checks):

1. Point `BannerTools` at WS2's server (change only `TOOL_NAMES` if names
   differ) and run the MCP tests and one live request.
2. Unknown student, unknown course, server down: the student sees only the
   fixed messages; logs show only codes and hashes.
3. A student with a current registration: the answer names the overlap, or
   says registrations could not be checked.
4. With WS4: two signed-in students at the same time get only their own
   data; a student ID typed in the chat changes nothing.

---

## 8. Constraints respected

- PRs #5 to #11 were not modified or merged (heads `7a783fa`, `027abcb`,
  `a0160b0`, `e7a3dbe`, `d4eacbf`, `abc9cc9`, `5a598d5`; all open).
- No code of Workstreams 1, 2 or 4 was changed. The new tool exists only in
  Workstream 3's fake server and is a proposal.
- `heldout2` was not run with a model and is identical to its
  pre-registration commit `0b4030e`. Its request texts were read while
  building D4 (see the disclosure in §3.4). Note: the handoff (§8.2) pins the
  `heldout2` run to PR #9's code (`d4eacbf`, expecting 428 tests). If this
  branch is merged before that run, the run must record the commit, the
  expected test count is 478, and the disclosure in §3.4 applies.
- No evaluation record was changed. No model evaluation was started.
- No secrets in the changed files: none shares 8 consecutive words with the
  system prompt, and none contains a token, key or password.

## 9. Next steps, by priority

1. Review this branch; open a pull request after approval (depends on #10).
2. Agree the WS2 contract additions (error codes, enrollments tool) and the
   OPEN team decisions in §6.
3. Run `heldout2` on the lab GPU as the handoff describes, stating which
   code it ran on.
4. Integrate with WS2, WS1 and WS4 and run the acceptance checks in §7.
5. Then: partial schedules (R1) and conversation history (R2), if in scope.

---

## 10. Quality pass (branch `fix/ws3-quality-pass`, 2026-10-20)

On top of PR #11 (`5a598d5`). Scope: Workstream 3 only. No model was run,
`heldout2` was not opened (its oracles only ran inside the unit tests), and
no evaluation evidence was changed.

### 10.1 Q1: current registrations

**Problem at PR #11.**
- Options were flagged, but the model could still say "you can take SEC2001"
  for an option that overlaps a current class; the fixed note came after a
  contradicting answer.
- The fallback answer listed such options under "Valid schedule options"
  with no label.
- An option that keeps the very section the student is already in counted
  as "repeats a registered course".
- A named section that overlaps a current class made `valid_together`
  false, mixing academic validity with registration fit.

**Fix.**
- Every option has `registration_fit`:
  - `fits_current_registration`: checked, no change needed;
  - `requires_registration_change`: switching sections of a registered
    course, an overlap with a current class, or the credit limit together
    with current classes;
  - `not_confirmed`: checked, but a current course's credits could not be
    read;
  - `not_checked`: registrations could not be listed.

  The tool result also has a `registration_summary` with the groups.
- Named sections get `fits_current_registration` and `registration_issues`,
  apart from `valid_together`.
- `registration_claims()` (`agent/evidence.py`) treats these like unsupported
  claims (one revision, then the fallback answer):
  - a sentence that names an option needing a change without stating the
    problem;
  - a sentence saying options fit current registrations when some do not,
    or when that could not be checked or confirmed.

  "No overlap" or "fits your current schedule" does not count as stating the
  problem.
- The fallback answer labels every option; the notes list the two groups
  separately.

**Unchanged.** Options are never removed (open team decision), and ranking
still puts fitting options first.

**Dev oracle answers.** The dev oracle answers for E03, E08, E10 and E11 now
state the overlap. They are in `evaluation/dev_oracle_registrations.json`;
`cases.json`, the expectations and the tool calls are unchanged.

### 10.2 Q2: hard constraints

**Problems at PR #11, all CONFIRMED by tests.** 23 of the new reading tests
fail on PR #11's code.

| Wording | At PR #11 | Now |
|---|---|---|
| "I must be done by 5pm, ideally by 3pm" | "conflicting", 15:00: the mandatory 17:00 was not enforced | 17:00 mandatory; the 15:00 wish is reported as not applied |
| "I can't do Fridays. Ideally no Mondays either." | both days "conflicting": Friday not enforced | Friday mandatory; the Monday wish is reported |
| "Avoid Fridays if you can, but Mondays are a must" | unclear and "conflicting": no question | clarification question |
| "No classes before 10, except on Tuesdays" | no class before 10 **and avoid Tuesdays** | limit for some days only: asked if mandatory |
| "Fridays are fine except after 3pm" | read as "start after 15:00" | some days only: not used as a limit |
| "Fridays aren't a problem, but I can't do Mondays" | avoid Fridays and Mondays | avoid Mondays only |
| "after 9.30", "5.30pm", "5:30 p.m." | cut by the sentence splitter ("after 9" = 09:00, **looser** than stated) | 09:30, 17:30 |
| "10am-3pm", "12-1" | dash ranges were never found | read; "free all day except 12-1" is a busy range |
| "around 10", "4ish", "9 or 10" | taken as exact | not exact: asked if mandatory |
| "done by 10 at night" | AM or PM unclear | 22:00 |

**How.** Strength is now read per fragment. If a preference has a mandatory
fragment and nothing relaxes it, only the mandatory and unsoftened fragments
decide its value and reliability. A wish stated next to a limit can neither
weaken the limit nor hide an unclear one. A relaxation ("... fine if I have
to", "Fridays aren't a problem") keeps the preference "conflicting", never
mandatory, as before.

**Check on development data.** On the 64 development requests (dev,
held-out, security live set), the readings are identical to PR #11's.

**Unreadable unsoftened limits.** A limit stated without a mandatory cue but
as a limit ("No classes Monday mornings.", "I work 8-10") that cannot be read
reliably, and that the model gave no value for, is asked about. It is treated
like a readable unsoftened limit, which is mandatory when the model leaves it
out.

**Weakening check against PR #11.** All 775 request-like strings were
compared: every request in the development datasets, plus every quoted string
in the test files except `heldout2`. Five mandatory limits of PR #11 are no
longer applied, and none of them is a real limit:
- three are misreadings that PR #11 made up: "Fridays aren't a problem" was
  read as "avoid Fridays";
- two are planner sentences in test files, not student requests ("both meet
  Tue/Thu 9:30-10:45" was read as "avoid Tuesday and Thursday").

No limit a student stated became weaker.

**Limits.**
- A wish next to a mandatory limit of the same kind is not used for ranking,
  because `plan_schedule` takes one value per preference; it is reported in
  `constraint_changes`.
- The clarification question needs R2 (conversation history) to be useful in
  a real chat: today the student's reply is a new single-turn request.

### 10.3 R7 and R9

- **R7.** `dev/stdio_server.py` chooses the data folder: `--data-dir`, else
  `UNA_DATA_DIR`, else `data/`. It checks the folder before starting and
  passes it to the subprocess as its only extra environment variable.
  `dev/chat.py` and `dev/demo_plan.py` use it and print the folder used.
- **R9.** Each model call's record also goes to the log of the request in
  progress (`agent/llm.py: call_log()`, a context variable).
  `AssistantResult.llm_calls` holds only that request's calls.
  - `run_eval.py` keeps those per case, once.
  - `OllamaLLM.stats` is now capped (last 1,000 calls), so a long-running
    server does not grow it forever.

### 10.4 Tests

**Local results:** 584 passed, 1 skipped, on Python 3.13 and on Python 3.12
(fresh virtual environment from `requirements.txt`), Linux.

**`tests/test_quality_pass.py` (78 tests):**
- registration fit per option and for named sections;
- answers that hide a needed change;
- notes and fallback labels;
- the dev oracle overlay;
- 22 reading cases (negation, exceptions, ambiguous times, mixed hard and
  soft);
- 10 unclear mandatory cases, and 3 unreadable unsoftened limits;
- assistant-level enforcement and clarification;
- the data folder over stdio and through the command-line tools;
- per-request model statistics under concurrency.

**Existing tests updated on purpose (4):**
- in `tests/test_evidence.py`, the scripted E08 and E11 answers of two
  parametrized tests now state the overlap;
- in `tests/test_integration_readiness.py`, two tests: the new note text, and
  keeping the section the student is already in is no change.

**`tests/test_prepublish_check.py` (28 tests):** see §10.5.

**CI** runs when this branch's pull request is opened.

### 10.5 Publication privacy

New files:
- **`CLAUDE.md`:** publication rules for Claude Code in this repository: no
  session or conversation links, no credentials, no automatic attribution
  footers or AI co-author trailers unless a policy requires them.
- **`ai-agent/dev/prepublish_check.py`:** a repeatable check of commit
  messages, added lines and PR or comment texts.
  - Its findings print category and location only, never the matched text.
  - `--install-hook` installs a local `commit-msg` hook.

The rules in `CLAUDE.md` are instructions. The script and the hook enforce
them only where they are run or installed.

**Windows fix (2026-10-21).** The first CI run of PR #12 failed three of these
tests on Windows; Ubuntu passed.
- **Encoding:** test fixtures with an emoji were written in the Windows
  default encoding (cp1252). The script also read git output that way. All
  of them are now explicitly UTF-8.
- **The hook:** the hook test required Unix executable bits, which Windows
  does not have. Git for Windows runs hooks without them, so that assertion
  now applies on Linux and macOS only.
- **The hook file:** it is now written with LF line endings and
  forward-slash paths, because a CRLF shell script would fail under Git for
  Windows' `sh`.
- **New tests:** two, covering the hook file format and UTF-8 commit messages
  and files.
- **Implicit encodings:** the privacy-check tests also pass with
  `-X warn_default_encoding -W error::EncodingWarning`, so they no longer use
  the platform default encoding anywhere.
