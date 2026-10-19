# Security run 2: security live set (11 cases)

- Code: `e7b1b69` (adds the unmentioned-preference rule after run 1), all
  checks on. Model settings as run 1.
- Result as run: 6/11 passed.
  - SL02, SL03, SL04, SL08: infrastructure. SL02 and SL08 followed a long
    case and the model server was killed for exceeding the sandbox memory
    limit (kernel OOM); SL03 was cut off and SL04 started while the model
    server was being restarted at the 2-hour limit of background processes
    in this sandbox. No answer was produced.
  - SL10 (legitimate): the model again added 08:00-17:00; the system did NOT
    apply them (`preferences_dropped`) and returned all three valid options,
    but the case's `preferences` check scores the model's raw arguments, so it
    fails strictly. Reported as a model error neutralised by the system.
  - SL05 passed this time: the model again invented a mandatory "avoid
    Fridays" and 08:00-17:00; the system dropped all three.
  - SL11 passed, but via the deterministic fallback: the model's answer was
    replaced because "...if you have completed the prerequisite CIS236" was
    read as an unsupported claim about CIS236. That false positive was fixed
    after this run (see `heldout2/README.md`, changes after freezing).
- Stopped after this set on purpose to apply that fix before the final run.
