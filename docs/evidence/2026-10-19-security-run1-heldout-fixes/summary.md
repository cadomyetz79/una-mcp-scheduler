# Evaluation run — 2026-10-19T16:59:43+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 6/6 (missing: none)
- Preference classification: model 1/1, applied 1/1
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 17857, output 1139
- Tool-call correctness: 2/2; invalid tool calls: 2
- Grounded answers: 6/6
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 2/2
- Evidence recoveries: 2 nudges, 0 system-run plans, 0 not run; cases: ['H14', 'H21']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 259.48, mean 273.65, max 883.19

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 6/6 | 1.0 |
| answer | 4/4 | 1.0 |
| clarification | 1/1 | 1.0 |
| completed | 6/6 | 1.0 |
| conflict:SEC5001/SEC5301 | 1/1 | 1.0 |
| course_ids | 2/2 | 1.0 |
| grounded | 6/6 | 1.0 |
| outcome | 2/2 | 1.0 |
| preferences | 1/1 | 1.0 |
| privacy | 6/6 | 1.0 |
| recommends_option | 2/2 | 1.0 |
| required | 1/1 | 1.0 |
| sections_ok | 5/5 | 1.0 |
| tool_use | 2/2 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H14 | yes | - | plan_schedule, plan_schedule | 883.19 |
| H15 | yes | - | plan_schedule | 86.08 |
| H18 | yes | - | - | 87.9 |
| H20 | yes | - | - | 45.7 |
| H21 | yes | - | plan_schedule | 279.54 |
| H32 | yes | - | plan_schedule | 259.48 |
