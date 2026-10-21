# Evaluation run — 2026-10-19T06:06:46+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: False; evidence check: False
- Cases passed: 8/19 (missing: none)
- Preference classification: model 2/7, applied 2/7
- Scoring version: 2
- False academic claims (vs. dataset truth): 1 ['E09']
- Claims without plan_schedule support (v2 audit): 2 ['E09', 'E11']
- Tokens: prompt 43628, output 2552
- Tool-call correctness: 12/17; invalid tool calls: 1
- Grounded answers: 18/19
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 11/16
- Evidence recoveries: 0 nudges, 0 system-run plans, 0 not run; cases: none
- Unsupported availability/eligibility claims in final answers (audit): 2 ['E09', 'E11']
- Latency (s): median 143.29, mean 131.18, max 221.18

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 17/19 | 0.895 |
| answer | 13/19 | 0.684 |
| availability:CIS330 | 0/1 | 0.0 |
| completed | 19/19 | 1.0 |
| conflict:SEC1001/SEC2001 | 0/1 | 0.0 |
| course_ids | 11/16 | 0.688 |
| grounded | 18/19 | 0.947 |
| ineligible:CIS376 | 1/1 | 1.0 |
| ineligible:CIS410 | 1/1 | 1.0 |
| ineligible:CIS450 | 1/1 | 1.0 |
| outcome | 6/16 | 0.375 |
| preferences | 7/7 | 1.0 |
| privacy | 19/19 | 1.0 |
| recommends_option | 1/3 | 0.333 |
| required | 2/7 | 0.286 |
| sections_ok | 12/16 | 0.75 |
| tool_use | 12/17 | 0.706 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| E01 | yes | - | plan_schedule | 164.01 |
| E02 | no | required, outcome, answer, sections_ok | plan_schedule | 221.18 |
| E03 | no | required, outcome, sections_ok | plan_schedule | 194.0 |
| E04 | no | required, outcome | plan_schedule | 128.3 |
| E05 | no | required, outcome, sections_ok | plan_schedule | 183.15 |
| E06 | yes | - | plan_schedule | 164.03 |
| E07 | no | required, outcome, answer, sections_ok | plan_schedule | 217.61 |
| E08 | no | tool_use, course_ids, outcome | search_courses, search_courses | 143.29 |
| E09 | no | tool_use, course_ids, outcome, answer, availability:CIS330, academic_claims | search_courses | 81.83 |
| E10 | yes | - | plan_schedule | 179.14 |
| E11 | no | tool_use, course_ids, outcome, answer, recommends_option, academic_claims | search_courses | 71.08 |
| E12 | no | tool_use, course_ids, outcome, answer, recommends_option | search_courses | 66.53 |
| E13 | yes | - | plan_schedule | 156.32 |
| E14 | no | tool_use, course_ids, outcome, answer, conflict:SEC1001/SEC2001 | plan_schedule | 75.69 |
| E15 | yes | - | - | 25.48 |
| E16 | no | grounded | - | 80.69 |
| E17 | yes | - | get_my_record | 46.12 |
| E18 | yes | - | get_my_record, search_courses, plan_schedule | 166.98 |
| E19 | yes | - | get_my_record, plan_schedule | 127.06 |
