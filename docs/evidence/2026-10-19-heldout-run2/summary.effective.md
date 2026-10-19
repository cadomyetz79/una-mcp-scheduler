# Evaluation run — 2026-10-19T13:05:09+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True
- Cases passed: 25/34 (missing: none)
- Preference classification: model 5/7, applied 6/7
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 121846, output 8724
- Tool-call correctness: 27/27; invalid tool calls: 5
- Grounded answers: 33/34
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 25/25
- Evidence recoveries: 11 nudges, 1 system-run plans, 0 not run; cases: ['H09', 'H11', 'H12', 'H13', 'H14', 'H16', 'H17', 'H22', 'H23', 'H27', 'H30']
- Unsupported availability/eligibility claims in final answers (audit): 1 ['H22']
- Latency (s): median 256.91, mean 294.88, max 733.43

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 34/34 | 1.0 |
| answer | 14/17 | 0.824 |
| availability:CIS340 | 1/1 | 1.0 |
| availability:CIS360 | 1/1 | 1.0 |
| availability:CIS480 | 2/2 | 1.0 |
| clarification | 0/3 | 0.0 |
| completed | 34/34 | 1.0 |
| conflict:SEC5001/SEC5301 | 0/1 | 0.0 |
| course_ids | 25/25 | 1.0 |
| grounded | 33/34 | 0.971 |
| ineligible:CIS360 | 1/1 | 1.0 |
| ineligible:CIS376 | 1/1 | 1.0 |
| ineligible:CIS450 | 2/2 | 1.0 |
| must_attempt | 1/1 | 1.0 |
| outcome | 24/25 | 0.96 |
| preferences | 7/7 | 1.0 |
| privacy | 34/34 | 1.0 |
| recommends_option | 8/9 | 0.889 |
| required | 6/7 | 0.857 |
| sections_ok | 27/28 | 0.964 |
| tool_use | 27/27 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H01 | yes | - | plan_schedule | 378.64 |
| H02 | yes | - | plan_schedule | 225.34 |
| H03 | yes | - | search_courses, get_my_record, plan_schedule | 307.75 |
| H04 | yes | - | plan_schedule | 520.75 |
| H05 | no | clarification | search_courses | 135.19 |
| H06 | yes | - | get_my_record, search_courses, search_courses, plan_schedule | 353.21 |
| H07 | yes | - | search_courses, search_courses, search_courses, plan_schedule | 727.26 |
| H08 | no | answer | plan_schedule | 256.91 |
| H09 | yes | - | search_courses, plan_schedule | 334.49 |
| H10 | yes | - | search_courses, search_courses, plan_schedule | 272.83 |
| H11 | yes | - | plan_schedule | 129.38 |
| H12 | yes | - | search_courses, plan_schedule | 339.21 |
| H13 | yes | - | search_courses, plan_schedule | 190.39 |
| H14 | no | conflict:SEC5001/SEC5301 | plan_schedule, plan_schedule | 648.05 |
| H15 | no | clarification | plan_schedule | 176.91 |
| H16 | yes | - | plan_schedule, plan_schedule | 341.62 |
| H17 | yes | - | plan_schedule | 277.31 |
| H18 | no | answer | - | 10.54 |
| H19 | yes | - | - | 16.67 |
| H20 | no | answer | - | 638.6 |
| H21 | no | grounded, sections_ok | - | 60.07 |
| H22 | yes | - | search_courses, get_my_record, plan_schedule, plan_schedule | 219.36 |
| H23 | yes | - | search_courses, plan_schedule | 296.43 |
| H24 | yes | - | search_courses, search_courses, plan_schedule | 733.43 |
| H25 | yes | - | search_courses, plan_schedule | 195.58 |
| H26 | yes | - | search_courses, get_my_record, plan_schedule | 178.94 |
| H27 | yes | - | search_courses, plan_schedule | 229.26 |
| H28 | yes | - | plan_schedule | 167.16 |
| H29 | yes | - | search_courses, search_courses, plan_schedule | 313.09 |
| H30 | yes | - | search_courses, plan_schedule | 665.47 |
| H31 | yes | - | plan_schedule | 210.91 |
| H32 | no | required, outcome, recommends_option | plan_schedule | 248.11 |
| H33 | yes | - | plan_schedule | 141.05 |
| H34 | no | clarification | get_my_record | 86.0 |
