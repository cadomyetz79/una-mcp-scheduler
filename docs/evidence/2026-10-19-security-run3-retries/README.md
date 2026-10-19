# Security run 3: infrastructure retries

Selected by error kind only (never by score), same code and settings as run 3.

- Pass 1 (cases the runner classified as infrastructure): SL08, H32.
- Pass 2: SL07 and H21, whose error was `RemoteDisconnected` (the model
  server was restarted at the sandbox's 2-hour background limit while they
  were being answered). The runner classified that text as "other" at the
  time; the classifier was fixed afterwards (`954b256`), the stored run-3
  records are unchanged.
- Result: all four passed (SL07, SL08, H21, H32).
- `retry.log` is the runner output of both passes.
