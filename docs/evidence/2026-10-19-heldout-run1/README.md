# Held-out evaluation — run 1 (qwen3:8b)

- Dataset: `ai-agent/evaluation/heldout/cases.json` (34 cases, pre-registered in commit `6429394`), data `ai-agent/evaluation/heldout/data`.
- System: all checks on. System code, prompt, MCP server and data identical to `6429394` for both parts (verified with `git diff` before part b).
- Model server: Ollama 0.40.6, CPU, context 4096, q8_0 KV cache, flash attention, one parallel slot; client timeout 300 s (default). Restarted between parts because of the 2-hour process limit.
- Part a: H01–H17, started 2026-10-19 09:22 UTC. Part b: H18–H34, started 10:37 UTC. Raw logs: `run-part-a.log`, `run-part-b.log`.
- Scored with the frozen assertions v2.0 (`summary.scoring-v2.0.*`, computed with the code at `6429394`) and with v2.1 (`summary.scoring-v2.1.*`). Both give the same result.
- Infrastructure failures (7: six client timeouts, one model-server crash after an out-of-memory kill): `INFRASTRUCTURE.md`. They were retried once with a 900 s timeout in a separate folder (`../2026-10-19-heldout-run1-infra-retry/`); the records here are unchanged.
