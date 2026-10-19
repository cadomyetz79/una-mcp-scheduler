# Ollama environment and first live runs — 2026-10-19 (cloud sandbox)

## Environment
- Machine: Linux x86_64, 2 vCPU, no GPU; process memory limit (cgroup) 5.84 GiB
- Ollama: 0.40.6, official release asset ollama-linux-amd64.tar.zst
- sha256 (published sha256sum.txt and local file match): c164ab8b1b28e2a247c29719b8e404c423c5b83ae64c3ab4e59d50c7ff7fc5e0
- Model: qwen3:8b, blob 4.87 GiB

## Run 0 — default server settings (context 8192): FAILED
- Error returned to the assistant: `Ollama returned 500: {"error":"llama-server process has terminated: signal: killed"}`
- Kernel log: Memory cgroup out of memory: Killed process 720 (llama-server) total-vm:6840200kB, anon-rss:5991672kB, file-rss:2652kB, shmem-rss:0kB, UID:0 pgtables:11876kB oom_score_adj:0
- Cause: weights (4.87 GiB) + 1152 MiB KV cache exceeded the 5.84 GiB limit.

## Fix used for all later runs
- Server: `OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_NUM_PARALLEL=1` (KV cache 306 MiB).

## Smoke test (direct /api/chat, default thinking on)
- Prompt "Reply with just the word OK.": answer "OK", 892 characters of thinking, 190 output tokens, 1.92 tok/s output, 118 s wall.

## Run 1 — full assistant, thinking off (dev/chat.py --no-think)
- Request: "I want to take CIS376 and CIS410 next spring. I'd prefer no classes before 10am if possible."
- Wall time: 387.96 s, model calls: 2, MCP calls: 6, grounded: True
- Model call 1: 989 prompt tokens in 139.51 s, 54 output tokens in 32.44 s, tool calls 1
- Model call 2: 1378 prompt tokens in 74.54 s, 210 output tokens in 139.55 s, tool calls 0
- Tool: plan_schedule {"required_preferences": ["earliest_start"], "course_ids": ["CIS376", "CIS410"], "earliest_start": "10:00"}
- Finding: the request said "I'd prefer ... if possible" (soft), but the model set required_preferences=["earliest_start"]. CIS376 was excluded (NO_SECTION_MATCHES_PREFERENCES) although SEC1001 + SEC2002 is valid with one soft miss. The answer was grounded but the outcome is wrong for the student's intent.
- Full record: docs/evidence/2026-10-19-ollama-live-01-qwen3-8b.json
