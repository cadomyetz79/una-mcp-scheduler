# Evaluation run — 2026-10-19T07:35:03+00:00

- Mode: live; model: qwen3:8b; think: False; num_ctx: 4096
- Machine: Linux x86_64 python 3.13.16
- Preference check: True
- Cases passed: 0/1 (missing: none)
- Preference classification: model 0/0, applied 0/0
- Tool-call correctness: 0/1; invalid tool calls: 1
- Grounded answers: 1/1
- Hard-constraint violations in returned options: 0
- Latency (s): median 87.41, mean 87.41, max 87.41

| Criterion | Passed | Rate |
|---|---|---|
| answer | 0/1 | 0.0 |
| completed | 1/1 | 1.0 |
| course_ids | 0/1 | 0.0 |
| grounded | 1/1 | 1.0 |
| outcome | 0/1 | 0.0 |
| privacy | 1/1 | 1.0 |
| tool_use | 0/1 | 0.0 |

| Case | Pass | Failed checks | Tools | Wall s |
|---|---|---|---|---|
| E14 | no | tool_use, course_ids, outcome, answer | plan_schedule | 87.41 |
