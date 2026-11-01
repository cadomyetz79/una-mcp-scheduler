# WS3 final offline regression (Step 5), 2026-11-01

| Item | Value |
|---|---|
| Owner | Hassan Alnabres (`ehassan256417-afk`), Workstream 3 |
| Code | team `main` at `052336f` (merge of PR #30), clean checkout |
| Environment | Windows 11, Python 3.15.1, pytest 9.2.0 |
| Data | synthetic only (repository `data/` and the bundled evaluation datasets) |
| Model | none. `RUN_OLLAMA_TESTS` and `UNA_DATA_DIR` unset; assistant tests use the scripted model (`ScriptedLLM`) |
| Not run | the `heldout2` live-model evaluation (Step 6, deferred to the lab GPU), any live Ollama run, CI |

## Commands and results

From `ai-agent/`:

```bash
python -m pytest -q -rs -p no:cacheprovider
```

**1036 passed, 1 skipped in 27.35 s**, exit code 0. The skip:
`tests/test_assistant.py:225` ("set RUN_OLLAMA_TESTS=1 with Ollama running").

From the repository root:

```bash
python -m pytest -q -rs -p no:cacheprovider tests/
```

**53 passed in 2.54 s**, exit code 0.

Syntax check of the optional live demo (not run):
`python -m py_compile scripts/live_team_mcp_chat.py`: compiles.

`PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` were used; `git status`
was clean afterwards.

## Tests collected per file

`ai-agent/tests/` (1037 collected):

| File | Tests | File | Tests |
|---|---|---|---|
| `test_assertions.py` | 7 | `test_quality_pass.py` | 78 |
| `test_assistant.py` | 17 | `test_ranking.py` | 9 |
| `test_evaluation.py` | 32 | `test_search_limit.py` | 29 |
| `test_evidence.py` | 32 | `test_section_details.py` | 112 |
| `test_fallback.py` | 13 | `test_security.py` | 94 |
| `test_heldout.py` | 57 | `test_security_assistant.py` | 50 |
| `test_heldout2.py` | 40 | `test_security_audit_fixes.py` | 33 |
| `test_integration_readiness.py` | 47 | `test_security_phase_b1.py` | 17 |
| `test_mandatory_constraints.py` | 44 | `test_strict_numeric_fields.py` | 158 |
| `test_mcp_planner.py` | 9 | `test_strict_record_fields.py` | 59 |
| `test_mock_dataset.py` | 10 | `test_validators.py` | 11 |
| `test_preference_language.py` | 51 | `test_prepublish_check.py` | 28 |

Repository root `tests/` (53 collected): `test_api.py` 28,
`test_team_backend_client.py` 12, `test_team_protected_mcp.py` 12,
`test_team_mcp_http_integration.py` 1.

## How to read these results

- **Offline only.** These tests check code paths with scripted model
  answers. They say nothing about how a real model answers.
- **`heldout2`.** `test_heldout2.py` replays the 37 pre-registered oracle
  answers through the real checks (plus 3 shape tests). This is the same
  check CI runs; it is not the `heldout2` evaluation, which needs a live
  model and has not been run.
- **Protected MCP.** `test_team_mcp_http_integration.py` runs the WS3
  `BannerTools`, planner and `SchedulingAssistant` (scripted model) against
  WS2's protected server over Streamable HTTP in process, with a synthetic
  signed token. No network, no live Entra login.
- **Not covered.** Python 3.12 and 3.13 and Linux (the CI matrix); no CI run
  pinned to `052336f` is recorded here.
