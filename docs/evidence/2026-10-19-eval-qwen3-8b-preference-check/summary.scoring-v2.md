# Evaluation run — 2026-10-19T06:48:41+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: False
- Cases passed: 13/19 (missing: none)
- Preference classification: model 2/7, applied 7/7
- Scoring version: 2
- False academic claims (vs. dataset truth): 1 ['E09']
- Claims without plan_schedule support (v2 audit): 2 ['E09', 'E11']
- Tokens: prompt 44195, output 2606
- Tool-call correctness: 12/17; invalid tool calls: 1
- Grounded answers: 18/19
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 11/16
- Evidence recoveries: 0 nudges, 0 system-run plans, 0 not run; cases: none
- Unsupported availability/eligibility claims in final answers (audit): 2 ['E09', 'E11']
- Latency (s): median 153.57, mean 142.79, max 250.47

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 17/19 | 0.895 |
| answer | 15/19 | 0.789 |
| availability:CIS330 | 0/1 | 0.0 |
| completed | 19/19 | 1.0 |
| conflict:SEC1001/SEC2001 | 0/1 | 0.0 |
| course_ids | 11/16 | 0.688 |
| grounded | 18/19 | 0.947 |
| ineligible:CIS376 | 1/1 | 1.0 |
| ineligible:CIS410 | 1/1 | 1.0 |
| ineligible:CIS450 | 1/1 | 1.0 |
| outcome | 11/16 | 0.688 |
| preferences | 7/7 | 1.0 |
| privacy | 19/19 | 1.0 |
| recommends_option | 1/3 | 0.333 |
| required | 7/7 | 1.0 |
| sections_ok | 16/16 | 1.0 |
| tool_use | 12/17 | 0.706 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| E01 | yes | - | plan_schedule | 181.2 |
| E02 | yes | - | plan_schedule | 230.03 |
| E03 | yes | - | plan_schedule | 250.47 |
| E04 | yes | - | plan_schedule | 202.31 |
| E05 | yes | - | plan_schedule | 153.57 |
| E06 | yes | - | plan_schedule | 169.61 |
| E07 | yes | - | plan_schedule | 228.78 |
| E08 | no | tool_use, course_ids, outcome | search_courses, search_courses | 143.42 |
| E09 | no | tool_use, course_ids, outcome, answer, availability:CIS330, academic_claims | search_courses | 85.59 |
| E10 | yes | - | plan_schedule | 178.96 |
| E11 | no | tool_use, course_ids, outcome, answer, recommends_option, academic_claims | search_courses | 73.83 |
| E12 | no | tool_use, course_ids, outcome, answer, recommends_option | search_courses | 69.3 |
| E13 | yes | - | plan_schedule | 175.62 |
| E14 | no | tool_use, course_ids, outcome, answer, conflict:SEC1001/SEC2001 | plan_schedule | 77.91 |
| E15 | yes | - | - | 25.14 |
| E16 | no | grounded | - | 84.21 |
| E17 | yes | - | get_my_record | 46.55 |
| E18 | yes | - | get_my_record, search_courses, plan_schedule | 185.32 |
| E19 | yes | - | get_my_record, plan_schedule | 151.28 |
