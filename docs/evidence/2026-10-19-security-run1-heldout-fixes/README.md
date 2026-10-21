# Security run 1: the six held-out failures, re-run

- Code: `0b4030e` (branch `feature/security-hardening`), all checks on.
- Model: qwen3:8b via Ollama 0.40.6, CPU, temperature 0, thinking off,
  context 4096, q8_0 KV cache, flash attention, `--num-predict 768`,
  client timeout 900 s.
- Cases: H14, H15, H18, H20, H21, H32 of the first held-out set, which is
  DEVELOPMENT data since this work (its failures were used to design the
  fixes). These results are development results, not generalisation evidence.
- Result: 6/6 passed (all six failed in both original held-out runs).
- Raw records: one JSON per case; `summary.json` / `summary.md` from the runner.
