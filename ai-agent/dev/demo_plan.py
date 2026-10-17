"""End-to-end demo: agent code -> MCP (stdio) -> fake server -> data/*.json.

    python dev/demo_plan.py S10001 2027SP CIS376 CIS410
    python dev/demo_plan.py S10001 2027SP CIS376 CIS410 --earliest 10:00

Prints the plan as JSON plus every MCP tool call that was made.
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

from agent.banner_tools import BannerTools  # noqa: E402
from agent.planner import Preferences, plan_schedules  # noqa: E402

SERVER = Path(__file__).resolve().with_name("fake_mcp_server.py")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("student_id")
    p.add_argument("term_id")
    p.add_argument("course_ids", nargs="+")
    p.add_argument("--earliest", help="HH:MM, no class before this")
    p.add_argument("--latest", help="HH:MM, no class after this")
    p.add_argument("--avoid", nargs="*", default=[], help="days, e.g. FRI")
    a = p.parse_args()

    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with Client(params) as client:
        tools = BannerTools(client)
        plan = await plan_schedules(
            tools, a.student_id, a.term_id, a.course_ids,
            Preferences(a.earliest, a.latest, tuple(a.avoid)),
        )
    print(json.dumps({"plan": plan.to_dict(), "mcp_calls": tools.calls}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
