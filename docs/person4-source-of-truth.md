# UNA MCP Scheduler
## Person 4 — Security, Integration & Testing | Source of Truth v1.0

**Document owner:** Bryson Black (Person 4)
**Evidence period:** October 25–November 1, 2026
**As-of date:** November 1, 2026
**Document purpose:** Individual workstream record for later consolidation into the team's professor-facing research report.
**Repository:** https://github.com/cadomyetz79/una-mcp-scheduler

> **Status of this document:** Initial reconstructed personal SOT. It records evidence shared and reviewed in the Person 4 development sessions; its initial preparation preceded repository publication; publication status is recorded in later updates. It has not been merged with an earlier team-wide “Source of Truth v0.3.” Review and preserve the original v0.3 separately if the team wishes to incorporate it.

## 1. How to interpret this source of truth

This is a record of Person 4's development actions, observations, decisions, open questions, and research evidence. It deliberately distinguishes a passing local test from an implemented, production-ready security capability.

| Evidence label | Meaning |
|---|---|
| **CONFIRMED** | Directly observed in code, Git output, test output, or screenshots supplied during these sessions. |
| **WORKING ASSUMPTION** | Plausible, but not yet independently tested or approved by the team. |
| **OPEN QUESTION** | Requires clarification, access, implementation, or further evidence. |
| **RECOMMENDATION** | Suggested next step; not evidence that it was adopted or completed. |

**Update rule:** Each new milestone should record its date, objective, workstream owner, branch/commit/PR, files changed, commands executed, observed results, security significance, limitations, and next action. Never silently change a past test result; add a dated follow-up entry instead.

## 2. Executive status snapshot

**CONFIRMED — Person 4 has prepared a reproducible Windows/WSL testing environment, created two testing contributions, verified the Mock Banner API and MCP security locally, and submitted GitHub pull requests.**

| Area | Last directly observed status | Evidence |
|---|---|---|
| AI agent baseline, earlier team revision | 643 passed, 1 skipped (live Ollama test), 0 failed; 9.45 s | Local `python -m pytest -v` in `ai-agent/` |
| First Mock Banner API contribution | 19 tests passed; commit `b025820`; PR #19 | `tests/test_api.py`, `requirements-dev.txt` |
| Updated Mock Banner API | 28 tests passed; 1 Starlette/HTTPX deprecation warning; 0.39 s | `python -m pytest tests/test_api.py -v` on updated main |
| Protected MCP, synthetic identity | 12 tests passed; 0.88 s | `tests/test_team_protected_mcp.py` |
| MCP HTTP integration, locally signed JWTs | 1 test passed; 0.79 s | `tests/test_team_mcp_http_integration.py` |
| New offline Entra JWT verifier tests | 14 tests passed; 1.00 s; commit `07fdbaf`; PR #34 | `tests/test_entra_token_verifier.py` |
| Combined root API/MCP/security suite | **67 passed, 0 failed; 1.30 s** | `python -m pytest tests/ -q` |
| Live university Entra sign-in and real identity mapping | **Not verified; awaiting approved university access** | Planned professor meeting |

**Important scope distinction:** The 67-test root suite is not the same as the earlier AI-agent suite; the 643-pass agent baseline was run on an earlier repository state and should not be reported as a current all-project combined result.

## 3. Person 4 responsibilities and system boundary

**Assigned role:** Security, Integration & Testing Engineer. Relevant responsibilities include testing API behavior, validating the MCP security boundary, supporting Entra authentication/integration, assessing student-level authorization, monitoring regression tests, and preserving reproducible research evidence.

**Inspected architecture, as designed:** A web application authenticates a student using Microsoft Entra; trusted server code validates the identity and binds a Banner student ID; an authenticated MCP connection exposes scheduling tools; the MCP server independently authorizes student-specific requests before calling the Mock Banner API; the AI agent uses the authorized tools to plan schedules.

**CONFIRMED implementation details:** The repository contains a Mock Banner FastAPI service (`app/main.py`), AI-agent code (`ai-agent/`), MCP security modules (`src/mcp_server/`), local security/integration tests (`tests/`), and synthetic academic JSON datasets (`data/`). The protected MCP implementation includes Entra-oriented token verification and student-record authorization. A fully deployed web application and end-to-end university sign-in have **not** been demonstrated in the reviewed evidence.

**Privacy boundary:** Local testing used synthetic academic records and synthetic identity claims. No real student records, real Entra tokens, passwords, or client secrets were used or added to tests.

## 4. Environment and reproducibility

**CONFIRMED environment:** Personal Windows computer; WSL2 Ubuntu Linux; VS Code; Git; `uv` 0.13.5; Python 3.13.17. Local repository: `~/una-mcp-scheduler`. Git remote: `https://github.com/cadomyetz79/una-mcp-scheduler.git`.

Separate Python virtual environments were established to avoid interfering with the AI agent's dependencies:

- **AI agent:** `ai-agent/.venv`, installed from `ai-agent/requirements.txt` using `uv` (MCP SDK and pytest). The original agent suite returned 643 passed and 1 skipped.
- **Root API/MCP environment:** `.venv`, installed initially with `requirements.txt`, pytest, and HTTPX; later supplemented from `requirements-mcp-dev.txt` for MCP testing. Both virtual environments are covered by `.gitignore`.
- **Relevant observed versions:** FastAPI 0.162.0; HTTPX 0.28.1; pytest 9.1.1; MCP SDK 2.3.0; PyJWT 2.15.1; `httpx2` 2.13.1; Python 3.13.17. These describe the observed local setup, not a general compatibility guarantee.

**Useful reproducibility commands** (run from repository root with the root `.venv` active):

```bash
source .venv/bin/activate
uv pip install --python .venv/bin/python -r requirements-mcp-dev.txt
python -m pytest tests/test_api.py -v
python -m pytest tests/test_team_protected_mcp.py -v
python -m pytest tests/test_team_mcp_http_integration.py -v
python -m pytest tests/test_entra_token_verifier.py -v
python -m pytest tests/ -q
```

**Known non-failing warning:** During the API runs, the installed FastAPI/Starlette test client emitted `StarletteDeprecationWarning` about using `httpx` rather than `httpx2`. The API tests still passed. Dependency migration should be handled deliberately rather than inferred from this warning alone.

## 5. Chronological activity and evidence log

### 5.1 October 25, 2026 — Establish the baseline

**Objective:** Create a local, independent testing setup for Person 4 work.
**Actions:** Cloned the team repository, confirmed GitHub access, established a clean Git state and feature branch, installed Python 3.13 through `uv`, created the AI-agent virtual environment, and ran the existing agent test suite.
**Observed result — CONFIRMED:** 644 tests collected: **643 passed, 1 skipped** in 9.45 seconds. The skipped live Ollama end-to-end case required `RUN_OLLAMA_TESTS=1` with Ollama running.
**Limitation:** This was the agent's existing test suite, not proof that live Entra authentication or the complete production API-to-MCP path worked.

### 5.2 October 25, 2026 — API reconnaissance and smoke tests

**Objective:** Identify uncovered testing/security work in `app/main.py`.
**Actions:** Inspected root API routes, dependencies, repository docs, current test files, and integration contract. Created a separate root `.venv` and exercised routes using FastAPI `TestClient`.
**Observed result — CONFIRMED:** Initial synthetic data consisted of **3 students, 6 courses, 5 sections, and 6 course-history records**. Smoke checks passed for health, list routes, detail lookups, and an unknown-student 404 response.
**Security finding — CONFIRMED from inspected code:** The Mock Banner API routes did not themselves implement caller authentication or record-level authorization. The team's documented MCP contract instead assigned user authentication and per-student access checks to trusted server/MCP components. Direct network exposure of personal-record endpoints remains a deployment concern; synthetic local test data does not make that architecture suitable for real student records.

### 5.3 October 25, 2026 — First permanent API regression suite

**Implementation:** Added `tests/test_api.py` and `requirements-dev.txt`. Coverage included health, list/detail routes, expected 404 responses, section filters, history filters, and student-specific course-history filtering.
**Observed result — CONFIRMED:** **19 passed, 0 failed**, in 0.28 seconds; one deprecation warning.
**Version-control evidence:** Branch `feature/person4-testing-baseline`; commit **`b025820`** (`Add Mock Banner API regression tests`); **151 lines added** across two files; pre-publication checker passed; pushed and submitted **PR #19**. On November 1, `git branch -r --contains b025820` listed `origin/main`, confirming inclusion of the commit in the remote main history.
**Pull request:** https://github.com/cadomyetz79/una-mcp-scheduler/pull/19

### 5.4 November 1, 2026 — Update to current team baseline

**Actions:** Fetched the latest remote history, updated local `main`, and created `feature/person4-security-readiness`. Reviewed additional team work: enrollment/term API routes, MCP integration and protected-server code, and security-related tests.
**Observed result — CONFIRMED:** Expanded API suite **28 passed, 0 failed** in 0.39 seconds, with the known warning. Relevant current modules included `src/mcp_server/team_security.py`, `entra_token_verifier.py`, `student_access.py`, and the MCP integration test files.
**Interpretation:** Updated documentation was not assumed to equal current implementation; code and test results were separately examined.

### 5.5 November 1, 2026 — Independently validate existing MCP security

**Actions:** Installed dependencies from `requirements-mcp-dev.txt` into root `.venv`. Ran the protected-MCP and signed-JWT HTTP integration tests.
**Observed results — CONFIRMED:** `tests/test_team_protected_mcp.py`: **12 passed in 0.88 seconds**; `tests/test_team_mcp_http_integration.py`: **1 passed in 0.79 seconds**.
**Security behaviors exercised:** Students reading own synthetic records; rejection of cross-student access; denial before an unauthorized backend call; missing scope and untrusted issuer rejection; safe structured backend errors; anonymous HTTP `401`; authenticated MCP calls over the HTTP protocol.
**Limitations:** Synthetic trusted contexts and locally signed JWTs were used. HTTP test key lookup was patched to a local test key. These results do **not** validate live Entra login, actual Microsoft JWKS retrieval/rotation, university account mapping, or production deployment.

### 5.6 November 1, 2026 — Second Person 4 security-testing contribution

**Implementation:** Created `tests/test_entra_token_verifier.py` with 14 offline JWT verification cases. Generated temporary RSA keys, supplied fake GUIDs/claims, and replaced the JWT key lookup with a controlled local public key. Added readable pytest IDs for oversized/malformed token cases.
**Scenarios:** Valid signed token; unauthorized signing key; wrong audience, tenant, issuer, scope, version, user object ID, and client ID; expired token; token not yet valid; empty, malformed, and oversized tokens.
**Observed results — CONFIRMED:** **14 passed in 1.00 seconds** after the test-name cleanup. The combined root suite `python -m pytest tests/ -q` reported **67 passed in 1.30 seconds**.
**Version-control evidence:** Branch `feature/person4-security-readiness`; commit **`07fdbaf`** (`Add offline Entra JWT security regression tests`); **150 lines added** in one new file; clean Git tree; commit and PR-description pre-publication checks passed; branch pushed; **PR #34** created. Screenshot showed **two successful GitHub checks**, no merge conflict, and an open PR. Team review and merge were not confirmed as of the last observation.
**Pull request:** https://github.com/cadomyetz79/una-mcp-scheduler/pull/34

## 6. Verified security architecture and gaps

### 6.1 Token-verifier behavior — code inspected; offline tests performed

`src/mcp_server/entra_token_verifier.py` is built for **single-tenant, delegated Microsoft Entra v2 access tokens**. It uses a tenant-specific Microsoft issuer and fixed JWKS endpoint; only `RS256` signatures are permitted. It checks signature, issuer, audience, required timing and identity claims, v2 token version, matching tenant, user object ID (`oid`), client ID (`azp`), and required `academic.read` scope. It rejects empty/oversized tokens and catches verification failures without accepting them. The current code uses a 30-second validation leeway. **These are implementation observations and offline test coverage, not a live Microsoft certification.**

### 6.2 MCP authorization — code inspected; synthetic tests passed

`src/mcp_server/student_access.py` maps a trusted `(tenant ID, object ID)` identity pair to a Banner student ID and rejects student-specific requests whose requested ID does not match that authorized mapping. `team_security.py` reads verified token context from the MCP authentication middleware; catalog tools also require an authenticated context and `academic.read`. When Entra tenant and API client IDs are both absent, token verification defaults to a reject-all verifier; providing only one configuration value raises an error. The default `STUDENT_LOOKUP` mapping is empty.

**CONFIRMED limitation:** No approved production identity-to-student mapping was supplied or verified in the inspected setup. A future mapping source must be server-controlled, privacy-preserving, and approved by the university.

### 6.3 Threats/limitations not yet closed

| Topic | Status / required follow-up |
|---|---|
| Live Microsoft authentication | **OPEN QUESTION:** No university tenant access or live token verification performed. |
| Real JWKS, key rotation, signing-key retrieval errors | **OPEN QUESTION:** Unit/HTTP tests stubbed key retrieval. Must validate the approved external configuration. |
| University account to Banner ID mapping | **OPEN QUESTION:** Default mapping is empty; approved data source and lifecycle are undecided. |
| Direct Mock Banner API exposure | **OPEN QUESTION:** Confirm backend network isolation or enforce suitable API authz before any use with real records. |
| Production logging, trace data and retention | **OPEN QUESTION:** MCP and agent traces may contain student data; determine access controls, retention, and redaction with the team. |
| Deployment boundaries, redirect URIs and API scopes | **OPEN QUESTION:** To be confirmed with the professor and university administrator. |
| Security test completeness | **RECOMMENDATION:** Add focused fail-closed configuration and unmapped-user tests only after checking existing coverage. |

## 7. Research and engineering decisions

| Date | Decision / practice | Rationale | State |
|---|---|---|---|
| Oct. 25 | Maintain isolated AI-agent and root API/MCP Python environments. | Avoid dependency interference; preserve reproducible results. | **CONFIRMED adopted** |
| Oct. 25 | Use synthetic academic records and FastAPI `TestClient` for API baseline. | Test locally without university systems or protected data. | **CONFIRMED adopted** |
| Oct. 25 | Submit code by feature branch and pull request; use required pre-publication check. | Preserve reviewability, attribution, and publication/privacy rules. | **CONFIRMED adopted** |
| Nov. 1 | Independently run the team's protected MCP and HTTP tests before creating new work. | Avoid duplicating another workstream's implementation. | **CONFIRMED adopted** |
| Nov. 1 | Add offline negative JWT tests before live Entra access. | Exercise fail-closed behavior without storing credentials. | **CONFIRMED adopted** |
| Nov. 1 | Keep an individual Person 4 SOT for later team consolidation. | Explicit team documentation plan; paper-ready traceability. | **CONFIRMED team plan reported; this file is its initial implementation** |
| Next phase | Implement and test approved live Entra integration only after professor/university authorization. | Requires tenant/app permissions and protected identity mapping. | **RECOMMENDATION / pending access** |

## 8. Planned work after Microsoft Entra access

**PLANNED — NOT YET EXECUTED.** Person 4 will work with the professor and team to validate the approved Microsoft Entra environment. The scope and exact sequence depend on permissions, the chosen web-app architecture, and available test identities.

1. **Obtain approved configuration:** Entra tenant ID, API application/client ID, approved client app registration or client configuration, redirect URI(s), `academic.read` delegated scope, and intended token audience. Use university-managed authorization; never request someone else's password or publish secrets.
2. **Validate real sign-in and token properties:** Confirm the approved client requests an access token **for the MCP API**, with the correct issuer, audience, tenant, token version, required scope, signature, and expiration. Distinguish access tokens from ID tokens.
3. **Validate approved student identity mapping:** Define who owns the `(tid, oid)` → Banner student ID mapping, how entries are created/revoked, and how an unknown or unmapped account is denied. Do not infer Banner IDs from user input or email addresses.
4. **Run authorization scenarios with approved test identities:** Student A may retrieve only A's data; Student B may retrieve only B's; A requesting B's records must be refused before backend retrieval. Verify missing-scope and unauthenticated paths where practical.
5. **Test integration and operational safeguards:** Confirm token attachment to MCP connection, HTTP behavior, JWKS availability/key rotation where feasible, frontend error handling, backend isolation, and diagnostic log privacy. Use synthetic or expressly approved data only.
6. **Record evidence for the research paper:** Approved environment description (without secrets), exact test commands, test-user categories without identifiers, outcomes, dates, limitations, failures/fixes, commit/PR links, and professor/team decisions.

### Questions to resolve with the professor

- Which Entra tenant and registered application(s) are approved for the prototype, and who administers them?
- Who exposes/consents to the `academic.read` API permission and configures valid redirect URIs?
- Can the team receive at least two distinct approved **test accounts** for student-isolation tests?
- How will authenticated Entra identities map to Banner student IDs, and who controls the mapping?
- Where will the MCP and Mock Banner services run, and how will direct backend/API access be restricted?
- What university policies govern logs, test data, secrets, retention, and demonstrations to the professor?

## 9. Open items and next-session checklist

| Priority | Action | Owner / dependency | Status |
|---|---|---|---|
| 1 | Check PR #34 review/merge outcome and address reviewer comments if any. | Person 4 + team reviewer | **OPEN**; last observed open |
| 2 | Request professor-approved Entra setup and two test identities. | Professor/university + team | **OPEN**; meeting planned |
| 3 | Decide who owns trusted student-identity mapping and its secure storage. | WS4 + WS2 + professor | **OPEN** |
| 4 | Review missing-config and unmapped-account coverage; add tests only if gaps remain. | Person 4 | **RECOMMENDATION** |
| 5 | Verify full agent suite against latest main when environment is ready. | Person 4 + team | **OPEN**; earlier 643-pass baseline is not a current all-suite rerun |
| 6 | Integrate each completed milestone into this personal SOT and later team master report. | Person 4 + team | **ONGOING** |

## 10. Evidence and citation index

**GitHub and code evidence**

- Repository: https://github.com/cadomyetz79/una-mcp-scheduler
- First contribution: https://github.com/cadomyetz79/una-mcp-scheduler/pull/19 — `b025820`; `tests/test_api.py`, `requirements-dev.txt`.
- Second contribution: https://github.com/cadomyetz79/una-mcp-scheduler/pull/34 — `07fdbaf`; `tests/test_entra_token_verifier.py`.
- Security implementation: `src/mcp_server/entra_token_verifier.py`, `student_access.py`, `team_security.py`, `team_protected_server.py`.
- Existing protected tests: `tests/test_team_protected_mcp.py`, `tests/test_team_mcp_http_integration.py`.
- Integration specification: `docs/workstream3-integration-contract.md` (especially §5 identity and authorization assumptions).
- Related documentation: `docs/workstream3-integration-audit.md`, `docs/workstream3-completion-summary.md`, `CLAUDE.md` (publication/privacy rules).

**Test commands and observed results**

| Test / command | Observed result |
|---|---|
| `cd ai-agent && python -m pytest -v` (earlier checkout) | 643 passed, 1 skipped in 9.45 s |
| `python -m pytest tests/test_api.py -v` (initial PR #19) | 19 passed in 0.28 s; one warning |
| `python -m pytest tests/test_api.py -v` (updated main) | 28 passed in 0.39 s; one warning |
| `python -m pytest tests/test_team_protected_mcp.py -v` | 12 passed in 0.88 s |
| `python -m pytest tests/test_team_mcp_http_integration.py -v` | 1 passed in 0.79 s |
| `python -m pytest tests/test_entra_token_verifier.py -v` | 14 passed in 1.00 s |
| `python -m pytest tests/ -q` | 67 passed in 1.30 s |
| `python ai-agent/dev/prepublish_check.py --range origin/main..HEAD --text-file /tmp/una-mcp-security-pr.md` | Passed before PR #34 publication |

**Evidence provenance:** Results were supplied through terminal transcripts and screenshots during Person 4 working sessions. This document does not itself rerun tests or confirm current GitHub status beyond those observations.

## 11. Revision and handoff rules

| Version | Date | Change |
|---|---|---|
| **v1.0** | November 1, 2026 | Initial individual Person 4 SOT reconstructed from the October 25 and November 1 development record; includes test baselines, PRs #19/#34, security analysis, open risks, and planned Entra testing. |

**For each future SOT revision:** keep the previous version; append evidence-linked milestones; mark completed versus planned work precisely; update the as-of date and status; never place credentials, real student identifiers, private session links, or sensitive logs in a shared copy. Before team publication, follow `CLAUDE.md` and run the repository's pre-publication checker on text that will leave the machine. The team's eventual consolidated SOT should reconcile multiple members' observations, rather than assuming they all describe the same code revision.

**Handoff summary:** Person 4's offline API and MCP security testing is established. The next significant research phase is approved live Microsoft Entra integration, student identity mapping, negative authorization testing, and end-to-end validation after the professor provides access.

## 12. Template for the next dated update

Copy and complete this template after the professor meeting, a new security test run, a reviewed pull request, or an integration change. Replace placeholders with observed facts, and keep open questions explicitly open until verified.

**Entry date / SOT version:** `[YYYY-MM-DD / v1.1]`
**Workstream owner:** `Person 4 — Security, Integration & Testing`
**Objective:** `[What we set out to verify or implement]`
**Context and dependencies:** `[Relevant team code revision, professor approval, environment; omit secrets]`
**Files and components changed:** `[Repository-relative paths; “none” for test-only observation]`
**Git evidence:** `[Branch, commit SHA, PR URL, review/merge status, if applicable]`
**Procedure:** `[Commands or reproducible steps without tokens or personal data]`
**Observed result:** `[Counts, errors, specific security behavior, or “not executed”]`
**Evidence label:** `[CONFIRMED / WORKING ASSUMPTION / OPEN QUESTION / RECOMMENDATION]`
**Security/privacy implication:** `[What was demonstrated and what was not]`
**Decision and rationale:** `[Who approved, what was decided, why; or “pending”]`
**Next action:** `[Owner and requirement for closure]`

**Pre-publication reminder:** For GitHub-bound text or changes, follow `CLAUDE.md`; do not publish real credentials, access tokens, private student data, or private session links. A passing synthetic test is not a substitute for approved live Entra validation.


---

## SOT status update — November 1, 2026

**Workstream:** Person 4 — Security, Integration & Testing

**CONFIRMED:** The repository's `main` branch was updated locally,
and `tests/test_entra_token_verifier.py` was present in the updated code.

**Git evidence:** CONFIRMED: Commit `07fdbaf` is included in `origin/main`.

**CONFIRMED:** The personal Source of Truth was copied to
`docs/person4-source-of-truth.md` on the separate branch
`docs/person4-source-of-truth`.

**DOCUMENTATION STATUS:** Repository commit, publication check,
and documentation pull request are pending as of this update.

**PLANNED:** After receiving approved Microsoft Entra access,
Person 4 will perform additional authentication and integration testing,
including real token validation, approved test-user access,
student identity mapping, and cross-student authorization checks.

**SECURITY LIMITATION:** Offline tests do not establish that
live university authentication or production authorization is ready.
