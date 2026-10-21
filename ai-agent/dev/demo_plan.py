"""End-to-end demo: agent code -> MCP (stdio) -> fake server -> data/*.json.

    python dev/demo_plan.py S10001 2027SP CIS376 CIS410
    python dev/demo_plan.py S10001 2027SP CIS376 CIS410 --earliest 10:00
    python dev/demo_plan.py S20002 2027SP CIS340 --data-dir evaluation/heldout/data

Prints the plan as JSON plus every MCP tool call that was made. --data-dir
(else UNA_DATA_DIR, else data/) selects the data the fake server reads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import Client  # noqa: E402

from agent.banner_tools import BannerTools  # noqa: E402
from agent.planner import PREFERENCE_NAMES, Preferences, plan_schedules  # noqa: E402
from dev.stdio_server import DataDirError, resolve_data_dir, server_params  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("student_id")
    p.add_argument("term_id")
    p.add_argument("course_ids", nargs="+")
    p.add_argument("--earliest", help="HH:MM, no class before this")
    p.add_argument("--latest", help="HH:MM, no class after this")
    p.add_argument("--avoid", nargs="*", default=[], help="days, e.g. FRI")
    p.add_argument("--soft", action="store_true",
                   help="treat the preferences as soft: rank schedules instead of filtering")
    p.add_argument("--data-dir", help="folder with the mock data JSON files (default: UNA_DATA_DIR, else data/)")
    a = p.parse_args()
    try:
        data_dir = resolve_data_dir(a.data_dir)
    except DataDirError as e:
        p.error(str(e))

    async with Client(server_params(data_dir)) as client:
        tools = BannerTools(client)
        plan = await plan_schedules(
            tools, a.student_id, a.term_id, a.course_ids,
            Preferences(a.earliest, a.latest, tuple(a.avoid), required=() if a.soft else PREFERENCE_NAMES),
        )
    print(json.dumps({"data_dir": str(data_dir), "plan": plan.to_dict(), "mcp_calls": tools.calls}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
