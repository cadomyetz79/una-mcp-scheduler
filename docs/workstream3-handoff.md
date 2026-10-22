# Workstream 3 handoff: AI Agent & Scheduling Logic

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`) |
| Date | 2026-10-19 |
| Code | `ai-agent/` in this repository |
| Latest code | Team `main` at `cfdaeb7`: PRs #5 to #12 merged on 2026-10-21 (this document was written at PR #9, head `d4eacbf`) |
| Status | Research prototype. **Not production-ready.** Current status, test results and remaining work: `docs/workstream3-completion-summary.md` (2026-10-22) |
| Integration fixes | PR #11 (defects D1 to D6, current registrations) and PR #12 (quality pass), see `docs/workstream3-integration-audit.md`. Contract for WS1, WS2 and WS4: `docs/workstream3-integration-contract.md` |

> **Status note (2026-10-22).** Sections 1, 3, 4 and 9 below describe the
> state on 2026-10-19, when PRs #5 to #9 were still open and the test count
> was 428. All of them are merged now and the count is 584 passed, 1 skipped.
> Section 8 (running `heldout2`) is still valid.

This document is for the team (Workstreams 1, 2 and 4) and for whoever runs
the second held-out evaluation on the lab GPU. Everything below is backed by
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
| Soft vs mandatory preferences, ranking | CONFIRMED, open (PR #5) |
| Live evaluation tooling and preference-strength check | CONFIRMED, open (PR #6) |
| Evidence orchestration and claim grounding | CONFIRMED, open (PR #7) |
| Held-out evaluation (34 cases, pre-registered) | CONFIRMED, open (PR #8) |
| Security hardening and second held-out set | CONFIRMED, open (PR #9) |
| Second held-out set (`heldout2`, 37 cases) | Pre-registered, **not run** (kept for the lab GPU) |
| Integration with the real Mock Banner API (WS1) | OPEN: the needed endpoints do not exist yet |
| Integration with the real MCP server (WS2) | OPEN: no WS2 server in the repo yet; the agent uses its own fake server |
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
| Fake MCP server | `dev/fake_mcp_server.py` | Serves `data/*.json` (or `UNA_DATA_DIR`) as 5 MCP tools until WS2's server exists |
| Planner | `agent/planner.py` | Course-level checks, then every section combination through `validate_schedule()`. Ranks by missed soft preferences. Reports truncation and search caps. Checks the student's own named sections as one combination (`requested_sections`). |
| Assistant loop | `agent/assistant.py` | Tool-calling loop with guardrails: bound identity and term, argument allow-list, course-ID vs section-ID schemas, step limit, one forced revision |
| Preference strength | `agent/preference_language.py` | Reads "must/can't" vs "if possible/rather" per preference. Relaxations make a wish "conflicting", which never overrides the model. Wishes the student never mentioned are not applied. |
| Evidence rules | `agent/evidence.py` | Availability and eligibility claims need a `plan_schedule` result. Section IDs must be grounded. "These sections work together" needs planner support. Unstated problems with named sections get a deterministic sentence. A bounded nudge and system-run plan cover missing evidence. |
| Trust boundaries | `agent/security.py` | Input inspection. Fake tool output and system markers are labelled as student text. Instruction-like text inside MCP data is removed before the model sees it. An output guard stops instruction and data leaks; logs keep only length and hash. |
| Safe answers | `agent/safe_answer.py` | An answer that leaks internal content gets a fixed refusal. An answer still unverified after the one revision is replaced by an answer built only from tool results. |
| Evaluation | `evaluation/` | Runner (live or oracle, ablations, retries, resume), scoring v1/v2 (v2.2), oracle validation, variability across runs, replay of rules on recorded answers, comparison reports |
| CI | `.github/workflows/ai-agent-tests.yml` | pytest on Ubuntu and Windows, Python 3.12 and 3.13 (4 jobs) |

Run it (from `ai-agent/`):

```bash
pip install -r requirements.txt          # Python 3.12 or 3.13
python -m pytest -q                      # expect: 428 passed, 1 skipped (the skip is the live
                                         # Ollama test; it runs with RUN_OLLAMA_TESTS=1)
python dev/demo_plan.py S10001 2027SP CIS376 CIS410          # planner only, no LLM
python dev/chat.py "I want CIS376 and CIS410, no classes before 10am"   # needs Ollama + qwen3:8b
```

---

## 3. Open PRs and dependency order

All five PRs come from the fork `ehassan256417-afk/una-mcp-scheduler-hassan`
into `cadomyetz79/una-mcp-scheduler:main`. They form one linear stack, each
built on the previous one (verified with `git merge-base`).

| Order | PR | Head | Content | CI (4 jobs) |
|---|---|---|---|---|
| 1 | #5 | `7a783fa` | Soft preferences and ranking in the planner | success |
| 2 | #6 | `027abcb` | Live Ollama evaluation (19 cases), preference-strength check | success |
| 3 | #7 | `a0160b0` | Evidence orchestration and claim grounding (dev set 19/19) | success |
| 4 | #8 | `e7a3dbe` | Held-out evaluation, 34 cases, pre-registered (25/34 in two runs) | success |
| 5 | #9 | `d4eacbf` | Security hardening, ID schemas, named-section checks, `heldout2` | success (428 passed, 1 skipped) |

Because every PR targets `main`, each one's diff also contains the PRs below
it. Merging is the repository owner's decision. Two safe options:

- **Option A:** merge #5, #6, #7, #8, #9 in this order with "Create a merge
  commit" (or "Rebase and merge").
- **Option B:** merge only #9, which contains everything, and close #5 to #8
  as included.

**Avoid "Squash and merge" for #5 to #8.** The later PRs still carry the
original commits, so squashing would cause conflicts or duplicate history.
None of these PRs touches Workstream 1's `app/` or `docs/mock-data-model.md`.

---

## 4. Test results

### Automated (CONFIRMED)

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

The only results that count as generalisation evidence are the 25/34 of the
first held-out set (PR #8). Everything after that is development data until
`heldout2` is run.

---

## 5. Known limitations (functional)

- **Single-turn only.** There is no conversation history.
- **No partial schedules.** If the requested courses cannot all fit, no
  "best 2 of 3" is offered.
- **Existing enrollments are not considered** (at PR #9). Fixed on
  `fix/integration-readiness` when the server has the optional
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

### Workstream 1: Mock Banner API (`app/`, PR #4 merged)

`app/main.py` currently serves `/health` and `/students`. The agent (through
WS2's MCP server) needs, per term `2027SP`:

| Data | Fields the agent reads (`scheduling/models.py`) |
|---|---|
| Student by ID | `student_id`, `max_credit_hours`, `active`; `program` (optional) |
| Course history by student | `course_id`, `term_id`, `status` (`completed` / `in_progress` / `failed` / `withdrawn`); `grade` (optional) |
| Course by ID and course search (text, subject) | `course_id`, `credit_hours`, `prerequisites[]`, `corequisites[]`; `title`, `subject` (for search) |
| Sections of a course in a term | `section_id`, `course_id`, `term_id`, `capacity`, `enrolled_count`, `meetings[]` with `days` (`MON`..`SUN`), `start_time`, `end_time` ("HH:MM", 24 h); `modality`, `location` (optional) |

Endpoint names are WS1's choice. The shapes above match `data/*.json` and
`docs/mock-data-model.md`. Questions for WS1 (OPEN):

- Is S10001's CIS330 really `completed` in 2026FA, or `in_progress`?
- Should `enrollments.json` count toward conflicts and credits?
- What are the real course and section ID formats (CRNs)?

### Workstream 2: MCP server

The agent's tool contract (WORKING ASSUMPTION; change names only in
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
  Proposed on `fix/integration-readiness`: a structured `error_code`
  (`"NOT_FOUND"`) instead of relying on the text, and no internal details
  (hosts, SQL, stack traces) in error texts. The agent shows only fixed
  messages either way.
- **Optional (proposed on `fix/integration-readiness`):**
  `get_student_enrollments(student_id, term_id)` returning the sections the
  student is already registered in, as full section records.
- **Results:** structured content (or JSON text). List results may be
  wrapped as `{"result": [...]}`.
- **Transport:** the agent uses `mcp.Client` (MCP Python SDK `>=2.2,<3`),
  over stdio today (`dev/chat.py`, `evaluation/run_eval.py`). A streamable
  HTTP server works by passing its transport to `Client`.
- **Authorization:** the server must enforce that a session only reads the
  authenticated student's records (WS4 token). Do not rely on the agent
  alone.
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

## 8. Running `heldout2` later (lab GPU)

`heldout2` (`ai-agent/evaluation/heldout2/`) was pre-registered in `0b4030e`
and has **never been run with a model**. Read
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
| 1 | Review and merge PRs #5 to #9 (order and method in §3) | Repository owner / team | everything below |
| 2 | Run `heldout2` once on the lab GPU (§8) and publish the report | Hassan, lab machine | the generalisation claim for the hardened system |
| 3 | Measure latency on the GPU; CPU numbers are not representative | Hassan | usability claim |
| 4 | Connect the agent to WS2's real MCP server; rename tools in `TOOL_NAMES` if needed; re-run the tests and one live smoke test | WS2 + Hassan | end-to-end system |
| 5 | WS1 endpoints for courses, history and sections; answer the three data questions in §7 | WS1 | item 4 |
| 6 | Replace the passed-in `student_id` with the Entra identity; MCP server authorization | WS4 + WS2 + Hassan | any real-user use |
| 7 | Decide the OPEN design questions: enrollments, partial schedules, `validate_schedule` as an MCP tool, real ID formats | Team | data and contract changes |
| 8 | A blind test set written by a teammate (especially attacks), and human review of answer quality for the paper | Team | stronger evaluation |
| 9 | Front end / chat history (multi-turn) and multi-turn security tests, if in scope | Team | multi-turn use |

Items 1 to 3 finish Workstream 3's own deliverables. Items 4 to 6 are
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

## 11. Sensitive-content check

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
