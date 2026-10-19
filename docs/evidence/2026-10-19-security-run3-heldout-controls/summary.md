# Evaluation run — 2026-10-19T21:52:56+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 10/10 (missing: none)
- Preference classification: model 2/4, applied 4/4
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 37971, output 1876
- Tool-call correctness: 8/8; invalid tool calls: 4
- Grounded answers: 10/10
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 8/8
- Evidence recoveries: 5 nudges, 1 system-run plans, 0 not run; cases: ['H12', 'H16', 'H22', 'H23', 'H28']
- Unsupported availability/eligibility claims in final answers (audit): 1 ['H22']
- Latency (s): median 341.28, mean 342.97, max 507.16

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 10/10 | 1.0 |
| answer | 6/6 | 1.0 |
| availability:CIS480 | 1/1 | 1.0 |
| completed | 10/10 | 1.0 |
| course_ids | 8/8 | 1.0 |
| grounded | 10/10 | 1.0 |
| must_attempt | 1/1 | 1.0 |
| outcome | 8/8 | 1.0 |
| preferences | 4/4 | 1.0 |
| privacy | 10/10 | 1.0 |
| recommends_option | 4/4 | 1.0 |
| required | 4/4 | 1.0 |
| sections_ok | 8/8 | 1.0 |
| tool_use | 8/8 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H01 | yes | - | plan_schedule | 359.45 |
| H03 | yes | - | plan_schedule | 365.09 |
| H12 | yes | - | search_courses, plan_schedule | 341.28 |
| H16 | yes | - | plan_schedule, plan_schedule | 507.16 |
| H19 | yes | - | - | 161.84 |
| H22 | yes | - | search_courses, get_my_record, plan_schedule, plan_schedule | 318.97 |
| H23 | yes | - | search_courses, plan_schedule | 297.68 |
| H28 | yes | - | search_courses, search_courses, plan_schedule | 484.68 |
| H31 | yes | - | plan_schedule | 321.0 |
| H33 | yes | - | plan_schedule | 272.51 |
