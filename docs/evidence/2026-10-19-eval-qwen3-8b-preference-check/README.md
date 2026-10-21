# Live evaluation — with the deterministic preference check (qwen3:8b)

- What: the same 19 cases as the baseline (`ai-agent/evaluation/cases.json`, version 2026-10-19), same model and server settings, run once.
- Code: commit `8adbc6d` (preference check enabled by default; same prompt, MCP server and data as the baseline at `12afb14`). The only differences seen by the run: the preference check, and the extra `preferences_applied` / `preference_corrections` fields it adds to each `plan_schedule` result.
- Command (from `ai-agent/`): `python evaluation/run_eval.py --model qwen3:8b --no-think --num-ctx 4096 --out <dir>`
- Ran 2026-10-19 06:48:41 → 07:33:54 UTC, directly after the baseline, on the same Ollama 0.40.6 server.

Files: `E01.json` … `E19.json` (raw records with score), `summary.json` / `summary.md`, `run.log`.
Comparison with the baseline: `../2026-10-19-eval-comparison.md` (and `.json`). Analysis: `../2026-10-19-eval-report.md`.
