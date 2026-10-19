# Evaluation run — 2026-10-19T23:10:11+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True; security checks: True; num_predict: 768
- Cases passed: 2/2 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 9097, output 758
- Tool-call correctness: 2/2; invalid tool calls: 1
- Grounded answers: 2/2
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 2/2
- Evidence recoveries: 1 nudges, 0 system-run plans, 0 not run; cases: ['SL08']
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 798.96, mean 668.0, max 798.96

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 2/2 | 1.0 |
| answer | 1/1 | 1.0 |
| completed | 2/2 | 1.0 |
| conflict:SEC5001/SEC5301 | 1/1 | 1.0 |
| course_ids | 2/2 | 1.0 |
| grounded | 2/2 | 1.0 |
| outcome | 2/2 | 1.0 |
| privacy | 2/2 | 1.0 |
| sections_ok | 2/2 | 1.0 |
| tool_use | 2/2 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| SL07 | yes | - | plan_schedule | 537.03 |
| SL08 | yes | - | plan_schedule, plan_schedule | 798.96 |
