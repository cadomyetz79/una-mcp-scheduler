# Evaluation run — 2026-10-19T12:54:38+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True
- Cases passed: 0/1 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 977, output 915
- Tool-call correctness: 0/0; invalid tool calls: 0
- Grounded answers: 1/1
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 0/0
- Evidence recoveries: 0 nudges, 0 system-run plans, 0 not run; cases: none
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 577.07, mean 577.07, max 577.07

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 1/1 | 1.0 |
| answer | 0/1 | 0.0 |
| completed | 1/1 | 1.0 |
| grounded | 1/1 | 1.0 |
| privacy | 1/1 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H20 | no | answer | - | 577.07 |
