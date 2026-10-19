# Live evaluation report 2 — evidence orchestration and claim grounding

Workstream 3. Follows `2026-10-19-eval-report.md` (baseline 8/19, preference
check 13/19). All numbers come from the raw records; each configuration was
run **once**. The two earlier runs are kept unchanged as historical evidence.

## 1. What was wrong (diagnosis from the raw records)

| Case | What the model did (preference-check run) | Category |
|---|---|---|
| E08 | `search_courses` ×2, answered from the catalog, never planned | missing tool call |
| E09 | `search_courses`, then "Yes, CIS330 is offered next spring" (false) | missing tool call + unsupported claim |
| E11 | `search_courses`, then "CIS410 is available", no sections | missing tool call + unsupported claim |
| E12 | `search_courses`, then asked the student for days/times | missing tool call |
| E14 | `plan_schedule` with an undeclared `section_ids` argument → rejected; then asked the student for permission | incorrect argument, then missing tool call |
| E16 | Correct refusal of the injection, naming SEC1002 (the section the student asked for) | genuine refusal; the section-ID grounding rule counted it as ungrounded |

No scoring error was found in these six cases at diagnosis time (see §5 for
one found later).

## 2. Intervention (`ai-agent/agent/evidence.py`, commit `aae1e98`)

Deterministic, from the request and the tool trace only:

- **Evidence requirement.** A request needs `plan_schedule` evidence if it is
  about taking / planning / availability and the course IDs are known: written
  in the request, or the single result of a search. Requests naming another
  student are skipped.
- **Bounded recovery.** If the model answers without that evidence: one
  nudge naming the missing call. If ignored, and the request has no time/day
  wording, the assistant runs `plan_schedule` itself once (`by: system`) and
  asks the model to answer from it; otherwise the answer is marked with the
  missing evidence. No further retries.
- **Claim grounding.** Availability/eligibility sentences ("is offered",
  "is available", "you can take", "not eligible") about a course need
  `plan_schedule` evidence: a positive claim needs the course in an option,
  a negative claim needs the course planned. The catalog alone is not enough.
- **Refusal-aware section grounding.** A section the student named may be
  mentioned in a sentence that rejects it (negation, "conflict", "full", ...).
  A section recommended outside the plan options is still ungrounded.

## 3. Results (live, qwen3:8b, CPU)

| Metric | Baseline (`12afb14`) | Preference check (`8adbc6d`) | Evidence check (`aae1e98`) |
|---|---|---|---|
| Cases passed (end to end) | 8/19 | 13/19 | **19/19** |
| Tool-call correctness, end to end | 12/17 | 12/17 | **17/17** |
| Model planned correctly without help | 11/16 | 11/16 | 11/16 |
| Model planned correctly after a nudge | – | – | 5/5 |
| Grounded (runtime check) | 18/19 | 18/19 | 19/19 |
| Unsupported availability claims in final answers (same rule applied offline to all runs) | 2 (E09, E11) | 2 (E09, E11) | **0** |
| Hard-constraint violations in returned options | 0 | 0 | 0 |
| Preference classification applied | 2/7 | 7/7 | 7/7 |
| Recoveries | – | – | 5 nudges; 0 system-run plans; 0 "not run" |
| Model calls / tool calls / MCP calls | 40 / 21 / 71 | 40 / 21 / 71 | 49 / 26 / 95 |
| Latency per case, mean / median (s) | 131 / 143 | 143 / 154 | 200 / 198 |
| Total wall time (s) | 2492 | 2713 | 3804 |
| Run errors / timeouts | 0 | 0 | 0 |

Case by case vs. the preference-check run
(`2026-10-19-eval-comparison-evidence.md`):

- **Fixed: E08, E09, E11, E12, E14, E16. New failures: none.**
- In E08, E09, E11, E12 and E14 the model's tool calls were **identical** to
  the previous run up to the nudge; after the nudge it called `plan_schedule`
  itself with the right course IDs. The comparison labels these
  "intervention".
- The 13 other cases: identical model tool calls in all 13; no nudge, no
  system-run tool.
- E09 now answers "CIS330 is not offered in the 2027SP term" from the plan
  result, and no false "offered" claim remains in any final answer.

## 4. Cost

- Each recovered case took 2 extra model calls (4 instead of 2) and 1 extra
  `plan_schedule`: E08 143 → 424 s, E09 86 → 218 s, E11 74 → 300 s,
  E12 69 → 229 s, E14 78 → 315 s.
- E16 got faster (84 → 36 s): its answer is identical, but no forced
  revision is needed any more.
- Cases with no recovery: mean 166.5 → 164.1 s excluding E01. E01 was
  slower (181 → 312 s) because the Ollama server had just been restarted:
  18 s model load and an uncached 976-token prompt (131 s).
- Overall mean latency +57 s per case (+40%), almost all from the five
  recovered cases. These are CPU timings.

## 5. What these results do NOT show

- **One run per configuration.** No variance estimate.
- **The rules were written after reading these six failures.** The fixed
  cases are the same cases that shaped the rules, so 19/19 is not evidence
  of generalisation. New, unseen requests are needed.
- **The system-run fallback never ran live.** The model followed every
  nudge. The fallback (system runs `plan_schedule`) and the "not run" path
  are tested only with scripted responses (`tests/test_evidence.py`).
- **E16 passes because the grounding rule changed, not the model.** Its
  answer is word-for-word the same as before. Applying the new section rule
  offline to the two earlier runs, their E16 answers would also count as
  grounded. The answer also asks the student for program details the
  assistant could read with `get_my_record` (quality issue, not scored).
- **E14 passes partly because of keyword scoring.** The answer gives the
  valid schedule SEC1001 + SEC2002 but does not tell the student that the
  SEC2001 they asked for conflicts; the `answer` check matched "conflict" in
  "has no conflicts". This is a weakness of the case definition, found
  after the run. The dataset was not changed afterwards, to keep runs
  comparable; a stricter E14 is proposed for dataset v2.
- Claim and evidence rules are English keyword rules; unusual phrasing can
  be missed.

## 6. Next steps

1. Dataset v2: unseen requests (paraphrases of every category, more topic
   searches with several matches, multi-turn follow-ups), and a stricter E14
   (the answer must say the requested SEC2001 conflicts).
2. Run each configuration 3 times; run on a lab GPU machine.
3. Have E16-type refusals use `get_my_record` instead of asking the student.
4. Extend claim grounding to prerequisites and credit totals.
