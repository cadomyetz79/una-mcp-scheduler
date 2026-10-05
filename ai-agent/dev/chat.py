"""Ask the scheduling assistant a question, end to end:

    student request -> LLM (Ollama) -> assistant tools -> planner
                    -> MCP (stdio) -> fake server -> data/*.json

Needs Ollama running with a tool-calling model pulled, e.g.:
    ollama pull qwen3:8b

    python dev/chat.py "I want CIS376 and CIS410, no classes before 10am"
    python dev/chat.py --student S10002 --model llama3.1:8b "Can I take CIS376?"
    python dev/chat.py --save ../docs/evidence/run.json "..."

--save writes the answer, the full tool trace and every MCP call as JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from agent.assistant import SchedulingAssistant  # noqa: E402
from agent.banner_tools import BannerTools  # noqa: E402
from agent.llm import OllamaLLM  # noqa: E402

SERVER = Path(__file__).resolve().with_name("fake_mcp_server.py")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("request")
    p.add_argument("--student", default="S10001")
    p.add_argument("--term", default="2027SP")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--save", help="write the full result as JSON to this path")
    a = p.parse_args()

    llm = OllamaLLM(model=a.model)
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with Client(params) as client:
        assistant = SchedulingAssistant(BannerTools(client), llm, a.student, a.term)
        result = await assistant.run(a.request)

    print(result.answer)
    print()
    print(f"[grounded={result.grounded} model_calls={result.model_calls} "
          f"tools={[t.tool for t in result.trace]} mcp_calls={len(result.mcp_calls)}]")
    if a.save:
        record = {"request": a.request, "student_id": a.student, "term_id": a.term,
                  "model": a.model, "result": result.to_dict()}
        Path(a.save).write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"saved to {a.save}")


if __name__ == "__main__":
    asyncio.run(main())
