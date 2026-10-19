# Held-out run 2 — retry of infrastructure failures

- Retried once: H08 and H31, the two run-2 cases that ended with a model-server crash (out-of-memory kill). Same settings as run 2 (timeout 900 s). Run-2 records are unchanged.
- Result: H31 passed; H08 failed the pre-registered keyword check, exactly as in run 1's retry (the answer says the "total credit hours exceed your limit").
