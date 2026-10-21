# Live evaluation — with evidence orchestration and claim grounding (qwen3:8b)

- What: the same 19 cases (`ai-agent/evaluation/cases.json`, version 2026-10-19, unchanged), same model and server settings as the two earlier runs, run once.
- Code: commit `aae1e98` (preference check + evidence check on). Working tree clean at start.
- Command (from `ai-agent/`): `python evaluation/run_eval.py --model qwen3:8b --no-think --num-ctx 4096 --out <dir>`
- Ran 2026-10-19 07:52:29 UTC → about 08:56 UTC on Ollama 0.40.6 (CPU, same settings: context 4096, q8_0 KV cache, flash attention, one parallel slot).
- The Ollama server was restarted with the same settings shortly before this run (its time limit was ending). E01 therefore includes a model load (18 s) and an uncached prompt (131 s); later cases do not.

Files: `E01.json` … `E19.json` (raw records with score; trace entries carry `by: model|system`, results carry `recoveries`, `unsupported_claims`, `rejected_section_mentions`, `evidence_missing`), `summary.json` / `summary.md`, `run.log`.

Comparisons: `../2026-10-19-eval-comparison-evidence.md` (vs. the preference-check run). Analysis: `../2026-10-19-eval-report-evidence.md`.
