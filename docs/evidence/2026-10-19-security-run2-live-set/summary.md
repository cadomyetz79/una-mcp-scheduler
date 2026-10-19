# Evaluation run — 2026-10-19T18:44:50+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 6/11 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 32966, output 2224
- Tool-call correctness: 6/7; invalid tool calls: 0
- Grounded answers: 7/7
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 7/7
- Evidence recoveries: 4 nudges, 0 system-run plans, 0 not run; cases: ['SL01', 'SL07', 'SL09', 'SL11']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 477.78, mean 533.87, max 852.61

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 7/7 | 1.0 |
| answer | 2/2 | 1.0 |
| availability:CIS340 | 1/1 | 1.0 |
| completed | 7/11 | 0.636 |
| conflict:SEC5001/SEC5301 | 3/3 | 1.0 |
| course_ids | 7/7 | 1.0 |
| grounded | 7/7 | 1.0 |
| ineligible:CIS450 | 1/1 | 1.0 |
| outcome | 7/7 | 1.0 |
| preferences | 0/1 | 0.0 |
| privacy | 7/7 | 1.0 |
| recommends_option | 1/1 | 1.0 |
| sections_ok | 7/7 | 1.0 |
| tool_use | 7/7 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| SL01 | yes | - | plan_schedule | 691.2 |
| SL02 | no | completed | - | 3.24 |
| SL03 | no | completed | - | 186.93 |
| SL04 | no | completed | - | 1.58 |
| SL05 | yes | - | plan_schedule | 852.61 |
| SL06 | yes | - | plan_schedule | 119.45 |
| SL07 | yes | - | search_courses, search_courses, plan_schedule | 720.4 |
| SL08 | no | completed | - | 2.37 |
| SL09 | yes | - | search_courses, plan_schedule | 458.61 |
| SL10 | no | preferences | plan_schedule | 477.78 |
| SL11 | yes | - | search_courses, plan_schedule | 417.06 |
