"""Ask the scheduling assistant a question, end to end:

    student request -> LLM (Ollama) -> assistant tools -> planner
                    -> MCP (stdio) -> fake server -> data/*.json

Needs Ollama running with a tool-calling model pulled, e.g.:
    ollama pull qwen3:8b

    python dev/chat.py "I want CIS376 and CIS410, no classes before 10am"
    python dev/chat.py --student S10002 --model llama3.1:8b "Can I take CIS376?"
    python dev/chat.py --save ../docs/evidence/run.json "..."
    python dev/chat.py --data-dir evaluation/heldout/data --student S20002 "Plan CIS340"

--save writes the answer, the full tool trace, every MCP call and this
request's model call statistics as JSON. --data-dir (else UNA_DATA_DIR, else
data/) selects the data the fake MCP server reads (dev/stdio_server.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import Client  # noqa: E402

from agent.assistant import SchedulingAssistant  # noqa: E402
from agent.banner_tools import BannerTools  # noqa: E402
from agent.llm import OllamaLLM  # noqa: E402
from dev.stdio_server import DataDirError, resolve_data_dir, server_params  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("request")
    p.add_argument("--student", default="S10001")
    p.add_argument("--term", default="2027SP")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--save", help="write the full result as JSON to this path")
    p.add_argument("--no-think", action="store_true", help="turn off the model's reasoning trace (faster)")
    p.add_argument("--num-ctx", type=int, help="context window to request from Ollama")
    p.add_argument("--data-dir", help="folder with the mock data JSON files (default: UNA_DATA_DIR, else data/)")
    a = p.parse_args()
    try:
        data_dir = resolve_data_dir(a.data_dir)
    except DataDirError as e:
        p.error(str(e))

    llm = OllamaLLM(model=a.model, think=False if a.no_think else None, num_ctx=a.num_ctx)
    started = time.perf_counter()
    async with Client(server_params(data_dir)) as client:
        assistant = SchedulingAssistant(BannerTools(client), llm, a.student, a.term)
        result = await assistant.run(a.request)
    wall = round(time.perf_counter() - started, 2)

    print(result.answer)
    print()
    print(f"[grounded={result.grounded} model_calls={result.model_calls} "
          f"tools={[t.tool for t in result.trace]} mcp_calls={len(result.mcp_calls)} wall={wall}s "
          f"data={data_dir}]")
    if a.save:
        record = {"request": a.request, "student_id": a.student, "term_id": a.term,
                  "model": a.model, "think": not a.no_think, "num_ctx": a.num_ctx, "data_dir": str(data_dir),
                  "wall_s": wall, "llm_calls": result.llm_calls, "result": result.to_dict()}
        Path(a.save).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"saved to {a.save}")


if __name__ == "__main__":
    asyncio.run(main())
