# Second held-out evaluation (`heldout2`) report — Workstream 3, Step 6

Aggregate results of two live runs of the pre-registered `heldout2` set.
Run IDs, configuration and checksums are in `2026-11-02-heldout2-provenance.md`.
The raw run records (model answers, tool traces, logs) are not published
here; they are retained unchanged outside the repository and can be checked
against the published SHA-256 values. Nothing below is extrapolated beyond
the tested conditions: one model (qwen3:8b), CPU only, synthetic data.

## 1. Method

- **Pre-registration.** Commit `0b4030e` froze the 37 cases, data, oracles, scoring v2 and run plan before any live run (`ai-agent/evaluation/heldout2/README.md`). The evaluated code is `d4eacbf` (PR #9); cases and data were checked against the freezing commit and the handoff §8.1 checksums in both runs.
- **Known before running.** One case was touched during oracle validation, and input inspection was predicted to flag exactly five attack requests; both are documented in the pre-registration README. Changes after freezing are listed there; none changed a case, expectation or oracle.
- **Execution.** Manual GitHub Actions workflow `.github/workflows/heldout2-eval.yml` (PRs #32, #33) on standard GitHub-hosted `ubuntu-24.04` runners (4 vCPU, 15.6 GiB RAM, no GPU), after a preflight that verified the environment without running any case. Run 2 is a repeat of run 1 with the identical configuration.
- **Settings.** qwen3:8b via Ollama 0.40.6, temperature 0, thinking off, context 4096, at most 768 output tokens, 900 s model timeout; flash attention, q8_0 KV cache, one parallel slot; every check on (preference strength, evidence, security).
- **Scoring.** Scoring v2.2 (written during the run) and v2.1 (re-scored with the scorer of the freezing commit, handoff §8.5); run-to-run comparison with `evaluation/variability.py` (§8.6).
- **Retries.** Infrastructure failures only, selected by error kind, never by score. None occurred, so none was made.
- **No system change** was made during or because of these results (handoff §8.7).

## 2. Results

| Metric | Run 1 | Run 2 |
|---|---|---|
| End-to-end success, scoring v2.2 | **23/37 (62.2 %)** | **23/37 (62.2 %)** |
| End-to-end success, scoring v2.1 | 23/37 (62.2 %) | 23/37 (62.2 %) |
| Infrastructure failures / retries | 0 / 0 | 0 / 0 |
| Preference classification, model alone / applied after the check (6 cases) | 3/6 / 4/6 | 2/6 / 3/6 |
| Tool-call correctness | 20/29 | 20/29 |
| Model made the right plan call itself | 22/27 | 22/27 |
| Recovery nudges / system-run plan fallback | 11 / 0 | 11 / 0 |
| Grounded answers (runtime check) | 37/37 | 37/37 |
| False academic claims (vs. dataset truth) | 1 | 1 |
| Positive availability/eligibility claims without plan support | 0 | 0 |
| Hard-constraint violations in returned options | 0 | 0 |
| Invalid tool calls (rejected by guardrails) | 3 | 3 |
| Latency per case: median / mean / max (s) | 90 / 118 / 363 | 108 / 136 / 448 |
| Model calls; tokens prompt / output | 90; 112,626 / 8,326 | 89; 111,011 / 7,996 |

Scoring v2.1 and v2.2 fail the same cases on the same checks in both runs.

### Failed cases by area

| Area | Run 1 | Run 2 |
|---|---|---|
| Planning not done or wrong courses for a plain request | 4 | 4 |
| Time/day wish handling (incl. one legitimate request worded like an attack) | 4 | 4 |
| Clarification not asked | 3 | 2 |
| Wrong answer content (inactive student, corequisite) | 2 | 2 |
| Schedule part of an override attempt (security handling passed) | 1 | 1 |
| Availability claim in a legitimate request worded like an attack | 0 | 1 |
| **Total failed** | **14** | **14** |

### Variability

- Same pass/fail in both runs: **35/37**. Of the 13 cases failing in both runs, 12 fail the same checks.
- Identical tool calls: 34/37. Identical final answer text: 6/37 (wording varies between runs even at temperature 0 on CPU).
- The failures are systematic, not run-to-run noise.

## 3. Security

| Item | Run 1 | Run 2 |
|---|---|---|
| Attack cases passed | 10/11 | 10/11 |
| Legitimate requests worded like attacks passed | 2/3 | 1/3 |
| Input inspection flagged exactly the five requests predicted before the run | yes | yes |
| Exfiltration answers blocked by the output guard | 2 | 1 |
| System-prompt text (8-word sequences) in any stored field | none | none |

- The failing attack case fails a scheduling check, not a security one.
- The attack requests that input inspection does not flag by design were all handled by the other layers (output guard, evidence rules, planner).
- Blocked answers are stored only as length and SHA-256; the student received the system fallback.

## 4. Limitations

- One model, CPU only, synthetic data. Latency depends on the CPU GitHub assigns (run 1 AMD EPYC 9V74, run 2 AMD EPYC 7763; run 2 about 14 % slower per case) and is not representative of a GPU.
- The set was written by the developer of the system rules (README "Not fully blind").
- Two runs, not three; the runs used a GitHub Actions CPU runner instead of the lab machine named in the handoff, with the pre-registered protocol otherwise unchanged.
- Only aggregates are published; per-case records are retained privately.

## 5. Conclusion

On the second held-out set the hardened system answers **23/37 (62.2 %)** requests end to end, identically in two runs and under both scoring versions, with no infrastructure failure. Every answer was grounded, no hard constraint was violated and there was one false claim per run. Security held for 10 of 11 attacks with no leak of internal instructions. The weaknesses are planning tool use for some plain requests, time/day wish handling, asking for clarification and answer content in two cases. Any system change made in response to these results would turn `heldout2` into development data.
