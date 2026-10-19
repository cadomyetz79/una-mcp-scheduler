# Held-out run 1 — retry of infrastructure failures

- Retried once: the 7 cases whose run-1 records ended with an infrastructure error (H04, H07, H08, H14, H20, H24, H30). Selection by error kind only (timeout or model-server failure), not by score.
- Same system, model and server settings as run 1, except the client timeout: **900 s** instead of 300 s. Run-1 records are unchanged in `../2026-10-19-heldout-run1/`.
- Result: H04, H07, H24, H30 passed; H08 failed the pre-registered keyword check (the answer says the "total credit hours exceed your limit" but not "credit limit"/"9 credit"); H14 failed the conflict assertion (valid options listed, but it never says the requested SEC5001 and SEC5301 conflict); H20 failed again with a model-server crash (out-of-memory kill at 07:18:11).
- H20 gets one more retry with a 1800 s timeout (`../2026-10-19-heldout-run1-infra-retry2/`); a first attempt at that was interrupted by the agent's own 10-minute foreground command limit after the model had generated for 9 min 53 s.
