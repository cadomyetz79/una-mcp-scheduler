# Held-out evaluation — run 2 (repeat of run 1)

- Same dataset, system (identical to pre-registration `6429394`), model and server settings as run 1, except the client timeout: **900 s** (run 1 used 300 s; its timeouts were infrastructure failures).
- Three parts (H01–H11, H12–H22, H23–H34), each with a freshly started Ollama server (2-hour process limit). Logs: `run-part-p1.log`, `run-part-p2.log`, `run-part-p3.log`.
- Result as run: 24/34. Infrastructure failures: H08 and H31 (model server killed by the kernel for running out of memory at 08:49:19 and 10:37:41, each right after a long generation in the previous case). Retried once in `../2026-10-19-heldout-run2-infra-retry/`.
