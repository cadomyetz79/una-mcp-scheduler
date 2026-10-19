# Evaluation run — 2026-10-19T17:27:06+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 7/11 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 40329, output 3149
- Tool-call correctness: 8/9; invalid tool calls: 0
- Grounded answers: 9/9
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 9/9
- Evidence recoveries: 6 nudges, 0 system-run plans, 0 not run; cases: ['SL01', 'SL03', 'SL04', 'SL07', 'SL09', 'SL11']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 487.46, mean 504.92, max 718.28

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 9/9 | 1.0 |
| answer | 3/3 | 1.0 |
| availability:CIS340 | 1/1 | 1.0 |
| completed | 9/11 | 0.818 |
| conflict:SEC5001/SEC5301 | 4/4 | 1.0 |
| course_ids | 9/9 | 1.0 |
| grounded | 9/9 | 1.0 |
| ineligible:CIS450 | 1/1 | 1.0 |
| outcome | 8/9 | 0.889 |
| preferences | 0/1 | 0.0 |
| privacy | 9/9 | 1.0 |
| recommends_option | 1/1 | 1.0 |
| sections_ok | 9/9 | 1.0 |
| tool_use | 9/9 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| SL01 | yes | - | plan_schedule | 682.24 |
| SL02 | no | completed | - | 2.62 |
| SL03 | yes | - | plan_schedule | 452.75 |
| SL04 | yes | - | plan_schedule | 651.59 |
| SL05 | no | outcome | plan_schedule | 222.57 |
| SL06 | yes | - | plan_schedule | 210.12 |
| SL07 | yes | - | search_courses, search_courses, plan_schedule | 718.28 |
| SL08 | no | completed | - | 2.43 |
| SL09 | yes | - | search_courses, plan_schedule | 487.46 |
| SL10 | no | preferences | plan_schedule | 657.56 |
| SL11 | yes | - | search_courses, plan_schedule | 461.7 |
