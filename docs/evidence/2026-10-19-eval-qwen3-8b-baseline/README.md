# Live evaluation — baseline (qwen3:8b, no preference check)

- What: the 19 cases in `ai-agent/evaluation/cases.json` (version 2026-10-19), run once through the real assistant, planner and fake MCP server (stdio) with a real model. No mocked model responses.
- Code: commit `12afb14` (before the preference check existed). The process started 2026-10-19 06:06:44 UTC; the files it reads per case (`ai-agent/prompts`, `ai-agent/dev`, `data/`) are unchanged between `12afb14` and the commits made while it ran.
- Command (from `ai-agent/`): `python evaluation/run_eval.py --model qwen3:8b --no-think --num-ctx 4096 --out <dir>`
- Model server: Ollama 0.40.6, CPU only (2 vCPU, 5.84 GiB memory limit), `OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_NUM_PARALLEL=1`, temperature 0, thinking off. See `../2026-10-19-ollama-environment-and-first-runs.md`.

Files:
- `E01.json` … `E19.json`: raw per-case records (request, full tool trace with arguments and results, every MCP call, answer, per-model-call tokens and timings) plus the score computed at run time.
- `run.log`: the runner's console output.
- `summary.original-runner.json/.md`: summary written by the runner at `12afb14`.
- `summary.json/.md`: the same records rescored with the current scorer (adds preference classification, tool-call correctness, hard-constraint re-validation). Case pass/fail is identical (8/19).
