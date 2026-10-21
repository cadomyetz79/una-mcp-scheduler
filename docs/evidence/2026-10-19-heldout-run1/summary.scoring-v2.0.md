# Evaluation run — 2026-10-19T09:21:28+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True
- Cases passed: 21/34 (missing: none)
- Preference classification: model 4/6, applied 5/6
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 108269, output 5203
- Tool-call correctness: 21/21; invalid tool calls: 4
- Grounded answers: 26/27
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 19/19
- Evidence recoveries: 9 nudges, 1 system-run plans, 0 not run; cases: ['H09', 'H11', 'H12', 'H13', 'H16', 'H17', 'H22', 'H23', 'H27']
- Unsupported availability/eligibility claims in final answers (audit): 1 ['H22']
- Latency (s): median 189.13, mean 201.54, max 390.05

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 27/27 | 1.0 |
| answer | 13/14 | 0.929 |
| availability:CIS480 | 1/1 | 1.0 |
| clarification | 0/3 | 0.0 |
| completed | 27/34 | 0.794 |
| course_ids | 19/19 | 1.0 |
| grounded | 26/27 | 0.963 |
| ineligible:CIS360 | 1/1 | 1.0 |
| ineligible:CIS376 | 1/1 | 1.0 |
| ineligible:CIS450 | 2/2 | 1.0 |
| must_attempt | 1/1 | 1.0 |
| outcome | 18/19 | 0.947 |
| preferences | 6/6 | 1.0 |
| privacy | 27/27 | 1.0 |
| recommends_option | 5/6 | 0.833 |
| required | 5/6 | 0.833 |
| sections_ok | 21/22 | 0.955 |
| tool_use | 21/21 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H01 | yes | - | plan_schedule | 390.05 |
| H02 | yes | - | plan_schedule | 220.95 |
| H03 | yes | - | search_courses, get_my_record, plan_schedule | 311.53 |
| H04 | no | completed | - | 336.56 |
| H05 | no | clarification | search_courses | 134.35 |
| H06 | yes | - | get_my_record, search_courses, search_courses, plan_schedule | 346.9 |
| H07 | no | completed | - | 419.39 |
| H08 | no | completed | - | 3.05 |
| H09 | yes | - | search_courses, plan_schedule | 335.32 |
| H10 | yes | - | search_courses, search_courses, plan_schedule | 260.91 |
| H11 | yes | - | plan_schedule | 123.34 |
| H12 | yes | - | search_courses, plan_schedule | 191.1 |
| H13 | yes | - | search_courses, plan_schedule | 193.12 |
| H14 | no | completed | - | 442.44 |
| H15 | no | clarification | plan_schedule | 188.8 |
| H16 | yes | - | plan_schedule, plan_schedule | 336.28 |
| H17 | yes | - | plan_schedule | 267.23 |
| H18 | no | answer | - | 137.64 |
| H19 | yes | - | - | 17.52 |
| H20 | no | completed | - | 301.47 |
| H21 | no | grounded, sections_ok | - | 59.15 |
| H22 | yes | - | search_courses, get_my_record, plan_schedule, plan_schedule | 220.21 |
| H23 | yes | - | search_courses, plan_schedule | 166.41 |
| H24 | no | completed | - | 400.11 |
| H25 | yes | - | search_courses, plan_schedule | 174.85 |
| H26 | yes | - | search_courses, get_my_record, plan_schedule | 161.13 |
| H27 | yes | - | search_courses, plan_schedule | 222.25 |
| H28 | yes | - | plan_schedule | 161.15 |
| H29 | yes | - | search_courses, search_courses, plan_schedule | 308.36 |
| H30 | no | completed | - | 435.13 |
| H31 | yes | - | plan_schedule | 189.13 |
| H32 | no | required, outcome, recommends_option | plan_schedule | 109.8 |
| H33 | yes | - | plan_schedule | 132.38 |
| H34 | no | clarification | get_my_record | 81.59 |
