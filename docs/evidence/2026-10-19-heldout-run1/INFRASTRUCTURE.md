# Held-out run 1 — infrastructure failures (server log evidence)

Client timeout 300 s (OllamaLLM default). Server log lines (Ollama GIN access log):
```
[GIN] 2026/10/19 - 04:42:26 | 500 |          5m0s |       127.0.0.1 | POST     "/api/chat"
[GIN] 2026/10/19 - 04:57:27 | 500 |          5m0s |       127.0.0.1 | POST     "/api/chat"
[GIN] 2026/10/19 - 04:57:30 | 500 |  1.282382708s |       127.0.0.1 | POST     "/api/chat"
[GIN] 2026/10/19 - 05:23:16 | 500 |          5m0s |       127.0.0.1 | POST     "/api/chat"
[GIN] 2026/10/19 - 05:44:56 | 500 |          5m0s |       127.0.0.1 | POST     "/api/chat"
[GIN] 2026/10/19 - 05:59:02 | 500 |          5m0s |       127.0.0.1 | POST     "/api/chat"
[GIN] 2026/10/19 - 06:23:25 | 500 |          5m0s |       127.0.0.1 | POST     "/api/chat"
```

Kernel OOM kills of llama-server (memory cgroup limit 5.84 GiB):
```
00:53:13 Memory cgroup out of memory: Killed process 720 (llama-server) total-vm:6840200kB, anon-rss:5991672kB, file-rss:2652kB, shmem-rss:0kB, UID:0
04:57:30 Memory cgroup out of memory: Killed process 6906 (llama-server) total-vm:6722564kB, anon-rss:5994480kB, file-rss:2732kB, shmem-rss:0kB, UID:
```

- H04 04:42:26, H07 04:57:27, H14 05:23:16, H20/H24/H30 (recorded as TimeoutError): model call exceeded 300 s.
- H08 04:57:30: model server returned 500 right after llama-server was killed by the kernel (out of memory) at about 04:57:30; the 00:53 kill is the earlier, documented setup failure.
