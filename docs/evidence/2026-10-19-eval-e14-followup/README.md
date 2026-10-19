# Single-case follow-up: E14 after the error-message fix

- Code: commit `b394782` (rejected tool arguments now name the tool, the rejected and the allowed arguments; section_ids gets a hint to plan by course_ids). Preference check on. Same model and server settings as the two full runs.
- Command: `python evaluation/run_eval.py --cases E14 --model qwen3:8b --no-think --num-ctx 4096 --out <dir>`
- Result: still FAIL. The model again sent `section_ids`; it received the new, specific error, replied "Let me check for available options", and ended its turn without calling `plan_schedule`. The fix removed a misleading message but did not change the outcome. This is one run of one case, not a full evaluation.
