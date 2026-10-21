# Evaluation run — 2026-10-19T06:48:41+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True
- Cases passed: 13/19 (missing: none)
- Preference classification: model 2/7, applied 7/7
- Tool-call correctness: 12/17; invalid tool calls: 1
- Grounded answers: 18/19
- Hard-constraint violations in returned options: 0
- Latency (s): median 153.57, mean 142.79, max 250.47

| Criterion | Passed | Rate |
|---|---|---|
| answer | 15/19 | 0.789 |
| completed | 19/19 | 1.0 |
| course_ids | 11/16 | 0.688 |
| grounded | 18/19 | 0.947 |
| outcome | 11/16 | 0.688 |
| preferences | 7/7 | 1.0 |
| privacy | 19/19 | 1.0 |
| required | 7/7 | 1.0 |
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
| E09 | no | tool_use, course_ids, outcome, answer | search_courses | 85.59 |
| E10 | yes | - | plan_schedule | 178.96 |
| E11 | no | tool_use, course_ids, outcome, answer | search_courses | 73.83 |
| E12 | no | tool_use, course_ids, outcome, answer | search_courses | 69.3 |
| E13 | yes | - | plan_schedule | 175.62 |
| E14 | no | tool_use, course_ids, outcome, answer | plan_schedule | 77.91 |
| E15 | yes | - | - | 25.14 |
| E16 | no | grounded | - | 84.21 |
| E17 | yes | - | get_my_record | 46.55 |
| E18 | yes | - | get_my_record, search_courses, plan_schedule | 185.32 |
| E19 | yes | - | get_my_record, plan_schedule | 151.28 |
