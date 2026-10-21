# Evaluation run — 2026-10-19T15:46:09+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True; evidence check: True
- Cases passed: 1/2 (missing: none)
- Preference classification: model 0/1, applied 1/1
- Scoring version: 2
- False academic claims (vs. dataset truth): 0 []
- Claims without plan_schedule support (v2 audit): 0 []
- Tokens: prompt 4570, output 302
- Tool-call correctness: 2/2; invalid tool calls: 0
- Grounded answers: 2/2
- Hard-constraint violations in returned options: 0
- Model made the right plan call itself: 2/2
- Evidence recoveries: 0 nudges, 0 system-run plans, 0 not run; cases: none
- Unsupported availability/eligibility claims in final answers (audit): 0 []
- Latency (s): median 256.91, mean 233.91, max 256.91

| Criterion | Passed | Rate |
|---|---|---|
| academic_claims | 2/2 | 1.0 |
| answer | 0/1 | 0.0 |
| completed | 2/2 | 1.0 |
| course_ids | 2/2 | 1.0 |
| grounded | 2/2 | 1.0 |
| outcome | 2/2 | 1.0 |
| preferences | 1/1 | 1.0 |
| privacy | 2/2 | 1.0 |
| recommends_option | 1/1 | 1.0 |
| required | 1/1 | 1.0 |
| sections_ok | 2/2 | 1.0 |
| tool_use | 2/2 | 1.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| H08 | no | answer | plan_schedule | 256.91 |
| H31 | yes | - | plan_schedule | 210.91 |
