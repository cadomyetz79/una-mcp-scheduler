# Evaluation run — 2026-10-19T11:40:36+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True
- Cases passed: 4/7 (missing: none)
- Preference classification: model 1/1, applied 1/1
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 24437, output 3047
- Tool-call correctness: 6/6; invalid tool calls: 1
- Grounded answers: 6/6
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 6/6
- Evidence recoveries: 2 nudges, 0 system-run plans, 0 not run; cases: ['H14', 'H30']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 695.77, mean 632.14, max 869.93

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 6/6 | 1.0 |
| answer | 1/2 | 0.5 |
| availability:CIS340 | 1/1 | 1.0 |
| availability:CIS360 | 1/1 | 1.0 |
| availability:CIS480 | 1/1 | 1.0 |
| completed | 6/7 | 0.857 |
| conflict:SEC5001/SEC5301 | 0/1 | 0.0 |
| course_ids | 6/6 | 1.0 |
| grounded | 6/6 | 1.0 |
| outcome | 6/6 | 1.0 |
| preferences | 1/1 | 1.0 |
| privacy | 6/6 | 1.0 |
| recommends_option | 3/3 | 1.0 |
| required | 1/1 | 1.0 |
| sections_ok | 6/6 | 1.0 |
| tool_use | 6/6 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H04 | yes | - | plan_schedule | 661.99 |
| H07 | yes | - | search_courses, search_courses, search_courses, plan_schedule | 767.85 |
| H08 | no | answer | plan_schedule | 126.58 |
| H14 | no | conflict:SEC5001/SEC5301 | plan_schedule, plan_schedule | 695.77 |
| H20 | no | completed | - | 3.01 |
| H24 | yes | - | search_courses, search_courses, plan_schedule | 869.93 |
| H30 | yes | - | search_courses, plan_schedule | 670.74 |
