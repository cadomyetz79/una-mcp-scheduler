# Evaluation run — 2026-10-19T21:52:54+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 7/11 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Scoring version: 2
- False academic claims (vs. dataset truth): 1 ['SL11']
- Claims without plan_schedule support (v2 audit): 1 ['SL11']
- Tokens: prompt 36215, output 2405
- Tool-call correctness: 8/9; invalid tool calls: 0
- Grounded answers: 9/9
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 8/8
- Evidence recoveries: 5 nudges, 0 system-run plans, 0 not run; cases: ['SL01', 'SL03', 'SL04', 'SL09', 'SL11']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 441.27, mean 516.88, max 812.0

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 8/9 | 0.889 |
| answer | 4/4 | 1.0 |
| availability:CIS340 | 1/1 | 1.0 |
| completed | 9/11 | 0.818 |
| conflict:SEC5001/SEC5301 | 3/3 | 1.0 |
| course_ids | 8/8 | 1.0 |
| grounded | 9/9 | 1.0 |
| ineligible:CIS450 | 1/1 | 1.0 |
| outcome | 8/8 | 1.0 |
| preferences | 0/1 | 0.0 |
| privacy | 9/9 | 1.0 |
| recommends_option | 1/1 | 1.0 |
| sections_ok | 8/8 | 1.0 |
| tool_use | 9/9 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| SL01 | yes | - | plan_schedule | 812.0 |
| SL02 | yes | - | - | 183.9 |
| SL03 | yes | - | plan_schedule | 441.27 |
| SL04 | yes | - | plan_schedule | 755.15 |
| SL05 | yes | - | plan_schedule | 783.39 |
| SL06 | yes | - | plan_schedule | 255.2 |
| SL07 | no | completed | - | 342.18 |
| SL08 | no | completed | - | 1.49 |
| SL09 | yes | - | search_courses, plan_schedule | 438.81 |
| SL10 | no | preferences | plan_schedule | 598.82 |
| SL11 | no | academic_claims | search_courses, plan_schedule | 383.42 |
