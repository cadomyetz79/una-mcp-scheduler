# Workstream 3 integration contract: what the AI Agent requires

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`), Workstream 3 (AI Agent & Scheduling Logic) |
| Date | 2026-10-22 |
| Code described | `ai-agent/` on team `main` at `cfdaeb7` (PRs #1 to #12 merged) |
| Status | **Proposal from Workstream 3.** Each item stays a WORKING ASSUMPTION until the owning workstream confirms it. |
| Related | `docs/workstream3-integration-test-checklist.md` (how to test it), `docs/workstream3-completion-summary.md` (status), `docs/mock-data-model.md` (WS1 data model) |

This document is for Workstreams 1, 2 and 4. It states what the agent sends,
what it needs back, how it handles errors, and what it assumes about
identity. Every statement is taken from the code on `main`; file references
are relative to `ai-agent/`.

Requirement levels:

- **REQUIRED**: without it the agent fails, or gives wrong or unsafe answers.
- **RECOMMENDED**: the agent works without it, but less safely or less well.
- **OPTIONAL**: the agent uses it when it exists.

---

## 1. Where Workstream 3 sits

```
Student (browser)
  -> WS4 web app (Entra sign-in; trusted server code)
       -> SchedulingAssistant(tools, llm, student_id, term_id)     agent/assistant.py
            -> LLM (Ollama, qwen3:8b by default)                    agent/llm.py
            -> BannerTools (MCP client, read-only)                  agent/banner_tools.py
                 -> WS2 MCP server
                      -> WS1 Mock Banner API (app/)
```

- The model never calls MCP tools directly. It sees three assistant tools
  (`get_my_record`, `search_courses`, `plan_schedule`). None of them takes a
  student ID.
- Academic decisions are made by code: `plan_schedules()` (`agent/planner.py`)
  only returns combinations that `validate_schedule()`
  (`scheduling/validators.py`) accepted.
- The agent only reads. It never registers, drops or changes anything.

---

## 2. Transport and connection (Workstream 2 and Workstream 4)

| # | Requirement | Level |
|---|---|---|
| T1 | An MCP server compatible with the MCP Python SDK `mcp>=2.2,<3` (tested with 2.2.0). | REQUIRED |
| T2 | Transport: Streamable HTTP (a URL) or stdio. `mcp.Client` accepts a URL, `StdioServerParameters`, a transport object, or an in-process server. | REQUIRED (one of them) |
| T3 | Authentication travels with the connection, for example an `Authorization` header on the HTTP transport (§5). | REQUIRED for real users |
| T4 | The caller sets a read timeout: `Client(..., read_timeout_seconds=N)`. A call that times out becomes `BackendUnavailable` (§4.3). The agent itself sets no timeout. The value is a joint WS2/WS4 decision. | RECOMMENDED |
| T5 | The server is read-only for the agent. | REQUIRED |

Connecting with a bearer token over Streamable HTTP. This exact pattern was
run on 2026-10-22 against the fake server on `127.0.0.1` (student record,
current registrations and a "not found" error all worked). The fake server
does not check the header; WS2's server must.

```python
from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.llm import OllamaLLM

http = create_mcp_http_client(headers={"Authorization": f"Bearer {access_token}"})
async with Client(streamable_http_client(mcp_url, http_client=http), read_timeout_seconds=10) as client:
    assistant = SchedulingAssistant(BannerTools(client), OllamaLLM(), student_id, term_id)
    result = await assistant.run(student_message)
```

`access_token`, `mcp_url`, `student_id` and `term_id` come from WS4's
server code (§5), never from the chat.

**One connection per signed-in student.** `BannerTools` keeps the calls of
concurrent requests apart (tested: `test_concurrent_students_on_one_mcp_session_never_see_each_other`),
but a connection opened with one student's token must not serve another
student.

---

## 3. MCP tools the agent calls

Tool names are mapped in one place, `agent/banner_tools.py: TOOL_NAMES`.
Renaming a tool is a one-line change there. **Argument names are fixed in
the `BannerTools` methods**; if WS2 uses other names (for example
`studentId`), those methods change too. All arguments are strings.

| Agent key | MCP tool | Arguments sent | Returns | Level |
|---|---|---|---|---|
| `student` | `get_student_record` | `student_id` | Student object (§3.1) | REQUIRED |
| `history` | `get_course_history` | `student_id` | List of course records (§3.2); `[]` if none | REQUIRED |
| `course` | `get_course` | `course_id` | Course object (§3.3) | REQUIRED |
| `search` | `search_courses` | `query`, `subject`: **both always sent**, `""` means "no filter" | List of course rows (§3.4) | REQUIRED |
| `sections` | `get_course_sections` | `course_id`, `term_id` | List of section objects (§3.5); **`[]` if the course is not offered that term, not an error** | REQUIRED |
| `enrollments` | `get_student_enrollments` | `student_id`, `term_id` | List of **full section objects** (§3.5) the student is registered in for that term; `[]` if none | OPTIONAL (strongly RECOMMENDED) |

When each tool is called:

- **Student record:** `get_student_record`, then `get_course_history`, for
  every `get_my_record` and every `plan_schedule` call.
- **Planning:** `plan_schedule` also calls `get_student_enrollments` (once),
  `get_course` for each requested course and each course the student is
  already registered in, and `get_course_sections` for each requested course.
- **Search:** `search_courses` only when the model searches the catalog.

### 3.1 Student (`get_student_record`)

| Field | Type | Level | Notes |
|---|---|---|---|
| `student_id` | string | REQUIRED | |
| `max_credit_hours` | integer | REQUIRED | Credit limit for the term |
| `active` | **JSON boolean** | REQUIRED | Must be `true`/`false`. A string is not rejected today: `"false"` is read as active (§7, G1). |
| `program` | string | optional | |

Extra fields are ignored. A missing required field gives
`BackendDataError`.

### 3.2 Course history record (`get_course_history`, list items)

| Field | Type | Level | Notes |
|---|---|---|---|
| `course_id` | string | REQUIRED | |
| `term_id` | string | REQUIRED | |
| `status` | string | REQUIRED | `completed`, `in_progress`, `failed`, `withdrawn`. Only `completed` satisfies a prerequisite (WORKING ASSUMPTION). |
| `grade` | string | optional | Not used for decisions (no minimum grades yet) |

### 3.3 Course (`get_course`)

| Field | Type | Level | Notes |
|---|---|---|---|
| `course_id` | string | REQUIRED | |
| `credit_hours` | integer | REQUIRED | |
| `prerequisites` | **JSON array** of course IDs | optional (default `[]`) | AND rule: all must be completed. A string is split into characters today (§7, G2). |
| `corequisites` | **JSON array** of course IDs | optional (default `[]`) | Satisfied if completed or in the same schedule |
| `title` | string | optional | |

### 3.4 Course search row (`search_courses`, list items)

`course_id` (string) is REQUIRED. `title`, `credit_hours`, `prerequisites`
and `corequisites` are optional. Filtering by `query` (text in the ID or
title) and `subject` (for example `CIS`) is done by the server.

### 3.5 Section (`get_course_sections` and `get_student_enrollments`, list items)

| Field | Type | Level | Notes |
|---|---|---|---|
| `section_id` | string | REQUIRED | Mock format `SEC` + digits (§6) |
| `course_id` | string | REQUIRED | |
| `term_id` | string | REQUIRED | Must equal the requested term |
| `capacity` | integer | REQUIRED | |
| `enrolled_count` | integer | REQUIRED | Full when `enrolled_count >= capacity` |
| `meetings` | array of meetings | optional (default `[]`) | A section without meetings never has a time conflict |
| `section_number`, `modality` | string | optional | |

Meeting:

| Field | Type | Level | Notes |
|---|---|---|---|
| `days` | JSON array | REQUIRED | Values from `MON TUE WED THU FRI SAT SUN`, upper case. `"Mon"` or a single string fails. |
| `start_time`, `end_time` | string | REQUIRED | 24-hour `"HH:MM"`; `"9:30 AM"` fails. `end_time` after `start_time`. |
| `location` | string | optional | |

Back-to-back meetings (one ends 10:45, the next starts 10:45) do not overlap.

### 3.6 How results are encoded

| Case | What the agent accepts |
|---|---|
| Object result | `structured_content` with the object |
| List result | `structured_content` as `{"result": [...]}` (the SDK does this for list return types) |
| No structured content | JSON in the text content |
| Anything else (HTML, plain text) | `BackendDataError` |

---

## 4. Errors

### 4.1 Tool errors (WS2)

| # | Requirement | Level |
|---|---|---|
| E1 | Report a failed lookup as an MCP tool error (`is_error: true`), not a crash or an empty success. | REQUIRED |
| E2 | Put a machine-readable code in the structured content of **every** error result: `{"error_code": "NOT_FOUND"}`. With a code present, the agent ignores the error text. | REQUIRED for real data |
| E3 | Error texts contain no internal details (hosts, SQL, stack traces, tokens). The agent never shows them, but other clients might. | REQUIRED |
| E4 | "No sections this term" is an empty list, not an error (§3). | REQUIRED |

Why E2 matters: without a code, "not found" is guessed from the text
(`not found`, `does not exist`, `no such`, `unknown student/course/section/term`).
A probe on 2026-10-22 returned the text `auth token not found` from
`get_student_record`; the agent told the model "Student record not found."
An authorization failure would then look like a missing student.

A real `MCPServer` tool can return a code like this (checked with SDK 2.2.0):

```python
from mcp import types

return types.CallToolResult(
    content=[types.TextContent(type="text", text="Course not found.")],
    structured_content={"error_code": "NOT_FOUND"},
    is_error=True,
)
```

Proposed codes and what the agent does with them today:

| `error_code` | Agent code | Fixed message given to the model | Effect |
|---|---|---|---|
| `NOT_FOUND` from `get_course` | `not_found` | "Course not found in the catalog." | The course is excluded as `UNKNOWN_COURSE`; planning continues |
| `NOT_FOUND` from `get_student_record` or `get_course_history` | `not_found` | "Student record not found." | No plan |
| `NOT_FOUND` from another tool | `not_found` | "Not found in the registration system." | That tool call fails |
| any other code (proposed: `FORBIDDEN`, `INVALID_ARGUMENT`, `UNAVAILABLE`, `INTERNAL`) | `tool_error` | "The registration system returned an error for this request." | That tool call fails |
| text "unknown tool" or "method not found" | `unknown_tool` | "This registration lookup is not available." | That tool call fails |

Mapping another code to its own message is a small Workstream 3 change once
WS2 publishes its list.

### 4.2 What the agent does with any backend failure

- **Raw text is never passed on.** The server's text and exception details
  never reach the model, the student or evaluation records. They are kept
  only as a SHA-256 prefix and a length (`BackendError.log_record()`), for
  matching with WS2's own logs.
- **Failures inside a tool call.** A failure during a model tool call is
  returned to the model as `{"error": <fixed message>, "error_code": <code>}`.
  The model's answer then goes through the normal checks.
- **Outages are not "missing".** A failing `get_course` is never reported as
  a course that does not exist; only `not_found` excludes a course.
- **Registrations.** A failing or missing `get_student_enrollments` gives
  "current registrations could not be checked"
  (`current_registrations_checked: false`). It is never treated as "no
  registrations".
- **Failures outside a tool call** (for example the model server) end the
  run with a fixed apology: `stopped_reason: "error"`,
  `answer_source: "system_error"`. `error` holds a category, the exception
  type and a hash, never the text.

### 4.3 Transport and data failures

| Failure | Agent error | Fixed message |
|---|---|---|
| Connection refused or closed, protocol error, read timeout | `BackendUnavailable` (`backend_unavailable`) | "The registration system is not reachable right now." |
| Wrong shape: missing field, `"Mon"`, `"9:30 AM"`, not JSON | `BackendDataError` (`backend_data_error`) | "The registration system returned data in an unexpected format." |

---

## 5. Identity and authorization assumptions

| # | Assumption | Owner | Enforced by the agent today |
|---|---|---|---|
| I1 | `student_id` is set by trusted server code from the validated Entra token, through a mapping to the Banner ID that the university controls. It is never taken from the chat text or from the model. | WS4 | The agent takes it only from `SchedulingAssistant(...)`. |
| I2 | `term_id` (for example `2027SP`) is chosen by the application, not by the student or the model. The agent does not read `terms.json`. | WS4 / WS1 | Bound at construction, like `student_id` |
| I3 | The model cannot choose whose data is read. | WS3 | Yes: no assistant tool takes an identity argument; any argument a tool does not declare is rejected, and identity-like names get a privacy message. |
| I4 | The agent sends `student_id` as an argument to `get_student_record`, `get_course_history` and `get_student_enrollments`. **The MCP server must check it against the authenticated user of the connection and refuse a mismatch** (an error with `error_code`, for example `FORBIDDEN`). The agent's binding is a second layer, not the authorization. | WS2 + WS4 | No (server side) |
| I5 | The user's token, or an on-behalf-of token for the MCP server, is attached to the MCP connection by WS4's server code (§2). | WS4 + WS2 | The agent never sees, logs or forwards a token to the model; `mcp_calls` holds only tool names, arguments and error codes. |
| I6 | One `SchedulingAssistant` per signed-in student, per request or per session. One MCP connection per signed-in student (§2). | WS4 | Concurrent `run()` calls on one assistant are isolated (tested). |
| I7 | Course and section data are not personal, but are read over the same authenticated connection. | WS2 | — |
| I8 | The model server sees the student's record and course history while it answers (§8). It must run on infrastructure the university approves (today: Ollama on a lab machine). | WS4 / team | — |

---

## 6. What WS4 gets back: `AssistantResult`

`await assistant.run(message)` never raises for backend or model failures.
It returns an `AssistantResult` (`agent/assistant.py`); `to_dict()` gives
JSON.

| Field | Use |
|---|---|
| `answer` | **The only text to show the student.** It is always present and always safe to show: on failures it is a fixed message. |
| `answer_source` | See the next table. |
| `stopped_reason` | `answered`, `max_steps` (fixed "couldn't finish" answer), `error` (fixed apology). |
| `clarification` | Non-empty when the answer is a question about an unclear required time or day limit; no schedule was built. |
| `registration_notes` | Fixed sentences already included in the answer, about current registrations. |
| `grounded` | `true` if every section ID in the returned answer comes from a planner option. |
| `error` | On `stopped_reason: "error"`: `{"kind", "type", "phase", "fingerprint"}`; never the exception text. |
| `llm_calls` | Timing and token counts of this request's model calls only. |
| `trace`, `mcp_calls`, `security`, `recoveries`, `blocked`, `unsupported_claims`, `registration_claims`, ... | Diagnostics. `trace` and `mcp_calls` **contain student data** (record, history, arguments). |

`answer_source`:

| Value | Meaning |
|---|---|
| `model` | The model's answer passed every check. |
| `model+system_note` | The model's answer, with sentences added by the application (for example a problem with a section the student named, or registration notes). |
| `system_fallback` | The model's answer failed a check twice or contained internal text. It was replaced by an answer built only from tool results (`blocked` says why). |
| `system_clarification` | A fixed question about an unclear required limit. |
| `system_error` | A fixed apology after a failure (§4.2). |

Requirements for WS4:

| # | Requirement | Level |
|---|---|---|
| W1 | Show `answer` only. Never show `trace`, `mcp_calls`, `security`, `error` or raw tool data. | REQUIRED |
| W2 | Decide logging and retention before real student data is used. Suggested default: log `answer_source`, `stopped_reason`, `error`, `security.backend_errors` (hashes only) and `llm_calls`; do not keep `trace` or `mcp_calls` for real students. | REQUIRED before real use |
| W3 | Allow for long requests. On a 2-vCPU CPU sandbox a request took 3 to 13 minutes; GPU latency is not measured yet. Each model call has a 300 s timeout (`OllamaLLM(timeout=300)`) and a request makes at most 8 model calls (`max_steps=8`). Use an asynchronous request with progress or a request-level timeout. | REQUIRED |
| W4 | Clarification replies (R2): there is no conversation history yet. Each `run()` is a new single-turn request, so a reply such as "10am" has no context. Until the team decides where conversation state lives, the student has to restate the request with an exact limit (§7, item G3). | REQUIRED to design |
| W5 | Opening the MCP connection (`async with Client(...)`) happens in WS4's code, before `run()`. If the server is down, that call raises (checked on 2026-10-22: the HTTP client raised an exception group wrapping a connection error). WS4 must catch it and show a fixed message, for example `agent.assistant.BACKEND_DOWN_ANSWER`, never the exception text. Failures after the connection is open are handled inside `run()` (§4.2). | REQUIRED |

---

## 7. Known gaps that affect the contract

| ID | Gap | Owner of the fix |
|---|---|---|
| G1 | `active` is read with `bool()`: the string `"false"` counts as active, so an inactive student could get options. JSON booleans (§3.1) avoid it; a strict check in `scheduling/models.py` is a small WS3 fix. | WS3 (small, independent); WS1/WS2 send booleans |
| G2 | `prerequisites` / `corequisites` given as a string are split into characters. This fails closed (the course is refused with a garbled reason), never open. | WS3 (small, independent); WS1/WS2 send arrays |
| G3 | A clarification answer only works when restated as a limit. Checked on 2026-10-22 with the deterministic reader: "I want CIS376. I can't do mornings. No classes before 10:00 AM." is resolved; the same request followed by "Earliest start: 10:00 AM." is asked about again. | WS4 + team decision (R2), then WS3 |
| G4 | Mock ID formats are hard-coded: course `^[A-Z]{2,4}\d{3}$`, section `^SEC\d+$` (`agent/assistant.py`, `agent/evidence.py`, `agent/preference_language.py`, `evaluation/assertions.py`). Real CRNs need these changed. | WS1 gives the formats, then WS3 |
| G5 | Only `NOT_FOUND` has its own handling; other codes are generic (§4.1). | WS2 publishes codes, then WS3 if needed |
| G6 | No partial schedules (R1), and options that conflict with current registrations are labelled, not removed. Both are open team decisions. | Team |

---

## 8. Data the model receives

So that WS4 can describe the data flow:

| Data | Source |
|---|---|
| The student's message | After the security check (`agent/security.py`) |
| Program, credit limit, active flag, list of completed courses | `get_my_record` |
| Course rows | `search_courses`: ID, title, credits, prerequisites, corequisites |
| Planner result | Options, exclusions, issues; current registrations by course and meeting time, with their section IDs removed |

The student ID itself is not in any tool result shown to the model. The
system prompt is `prompts/system.md`; it is in the repository and is not a
secret.

---

## 9. Configuration

| Setting | Where | Default |
|---|---|---|
| Model server | `OLLAMA_HOST` or `OllamaLLM(host=...)` | `http://localhost:11434` |
| Model | `OllamaLLM(model=...)` | `qwen3:8b` |
| MCP tool names | `agent/banner_tools.py: TOOL_NAMES` | names in §3 |
| Mock data folder (fake server only) | `--data-dir`, else `UNA_DATA_DIR`, else `data/` | `data/` |
| Python | 3.12 or 3.13 | `ai-agent/requirements.txt` |

## 10. Changing this contract

1. The owning workstream proposes the change (names, fields, codes, ID formats).
2. Workstream 3 updates `TOOL_NAMES`, the `BannerTools` methods,
   `scheduling/models.py` or the ID patterns, and this document.
3. Workstream 3 re-runs `python -m pytest -q` and the checklist in
   `docs/workstream3-integration-test-checklist.md`.
