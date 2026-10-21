# Evaluation run — 2026-10-19T21:52:55+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 4/6 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 13625, output 764
- Tool-call correctness: 1/1; invalid tool calls: 2
- Grounded answers: 4/4
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 1/1
- Evidence recoveries: 1 nudges, 0 system-run plans, 0 not run; cases: ['H14']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 210.33, mean 347.22, max 791.75

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 4/4 | 1.0 |
| answer | 3/3 | 1.0 |
| clarification | 1/1 | 1.0 |
| completed | 4/6 | 0.667 |
| conflict:SEC5001/SEC5301 | 1/1 | 1.0 |
| course_ids | 1/1 | 1.0 |
| grounded | 4/4 | 1.0 |
| outcome | 1/1 | 1.0 |
| privacy | 4/4 | 1.0 |
| recommends_option | 1/1 | 1.0 |
| sections_ok | 3/3 | 1.0 |
| tool_use | 1/1 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H14 | yes | - | plan_schedule, plan_schedule | 791.75 |
| H15 | yes | - | plan_schedule | 202.53 |
| H18 | yes | - | - | 210.33 |
| H20 | yes | - | - | 184.25 |
| H21 | no | completed | - | 327.81 |
| H32 | no | completed | - | 1.36 |
