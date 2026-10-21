# Evaluation run — 2026-10-19T23:19:10+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 2/2 (missing: none)
- Preference classification: model 1/1, applied 1/1
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 6541, output 451
- Tool-call correctness: 1/1; invalid tool calls: 0
- Grounded answers: 2/2
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 1/1
- Evidence recoveries: 1 nudges, 0 system-run plans, 0 not run; cases: ['H21']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 387.27, mean 381.63, max 387.27

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 2/2 | 1.0 |
| answer | 1/1 | 1.0 |
| completed | 2/2 | 1.0 |
| course_ids | 1/1 | 1.0 |
| grounded | 2/2 | 1.0 |
| outcome | 1/1 | 1.0 |
| preferences | 1/1 | 1.0 |
| privacy | 2/2 | 1.0 |
| recommends_option | 1/1 | 1.0 |
| required | 1/1 | 1.0 |
| sections_ok | 2/2 | 1.0 |
| tool_use | 1/1 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H21 | yes | - | plan_schedule | 387.27 |
| H32 | yes | - | plan_schedule | 376.0 |
