# Evaluation run — 2026-10-19T07:52:29+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True
- Cases passed: 18/19 (missing: none)
- Preference classification: model 2/7, applied 7/7
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 57133, output 3289
- Tool-call correctness: 17/17; invalid tool calls: 1
- Grounded answers: 19/19
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 16/16
- Evidence recoveries: 5 nudges, 0 system-run plans, 0 not run; cases: ['E08', 'E09', 'E11', 'E12', 'E14']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 198.48, mean 200.19, max 424.19

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 19/19 | 1.0 |
| answer | 19/19 | 1.0 |
| availability:CIS330 | 1/1 | 1.0 |
| completed | 19/19 | 1.0 |
| conflict:SEC1001/SEC2001 | 0/1 | 0.0 |
| course_ids | 16/16 | 1.0 |
| grounded | 19/19 | 1.0 |
| ineligible:CIS376 | 1/1 | 1.0 |
| ineligible:CIS410 | 1/1 | 1.0 |
| ineligible:CIS450 | 1/1 | 1.0 |
| outcome | 16/16 | 1.0 |
| preferences | 7/7 | 1.0 |
| privacy | 19/19 | 1.0 |
| recommends_option | 3/3 | 1.0 |
| required | 7/7 | 1.0 |
| sections_ok | 16/16 | 1.0 |
| tool_use | 17/17 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| E01 | yes | - | plan_schedule | 311.65 |
| E02 | yes | - | plan_schedule | 231.01 |
| E03 | yes | - | plan_schedule | 242.4 |
| E04 | yes | - | plan_schedule | 198.48 |
| E05 | yes | - | plan_schedule | 153.24 |
| E06 | yes | - | plan_schedule | 177.75 |
| E07 | yes | - | plan_schedule | 234.29 |
| E08 | yes | - | search_courses, search_courses, plan_schedule | 424.19 |
| E09 | yes | - | search_courses, plan_schedule | 217.84 |
| E10 | yes | - | plan_schedule | 168.17 |
| E11 | yes | - | search_courses, plan_schedule | 300.18 |
| E12 | yes | - | search_courses, plan_schedule | 229.48 |
| E13 | yes | - | plan_schedule | 168.32 |
| E14 | no | conflict:SEC1001/SEC2001 | plan_schedule, plan_schedule | 315.0 |
| E15 | yes | - | - | 24.92 |
| E16 | yes | - | - | 35.56 |
| E17 | yes | - | get_my_record | 43.86 |
| E18 | yes | - | get_my_record, search_courses, plan_schedule | 182.92 |
| E19 | yes | - | get_my_record, plan_schedule | 144.31 |
