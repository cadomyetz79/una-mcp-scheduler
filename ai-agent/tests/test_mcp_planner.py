"""Agent <-> MCP tests against the fake server (dev/fake_mcp_server.py).

Most tests connect in-process (fast). test_stdio_end_to_end launches the
server as a real subprocess and talks MCP over stdin/stdout, the same way
the agent will reach the real server.
"""

import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agent.banner_tools import TOOL_NAMES, BannerTools, ToolCallError
from agent.planner import Preferences, plan_schedules
from dev.fake_mcp_server import server

pytestmark = pytest.mark.anyio

TERM = "2027SP"
SERVER_PATH = Path(__file__).resolve().parents[1] / "dev" / "fake_mcp_server.py"


def codes(plan):
    return {e.course_id: e.code for e in plan.excluded}


# ---------------------------------------------------------------- MCP layer


async def test_server_exposes_expected_tools():
    async with Client(server) as client:
        listed = {t.name for t in (await client.list_tools()).tools}
    assert set(TOOL_NAMES.values()) <= listed


async def test_student_is_loaded_through_mcp():
    async with Client(server) as client:
        tools = BannerTools(client)
        student = await tools.student("S10001")
    assert student.max_credit_hours == 18
    assert student.completed_courses == {"CIS225", "CIS236", "CIS330"}
    assert [c["tool"] for c in tools.calls] == ["get_student_record", "get_course_history"]


async def test_unknown_student_is_an_error_not_a_crash():
    async with Client(server) as client:
        with pytest.raises(ToolCallError):
            await BannerTools(client).student("S99999")


# ---------------------------------------------------------------- planner


async def test_plan_finds_only_conflict_free_open_option():
    # CIS376: SEC1001 open, SEC1002 full. CIS410: SEC2001 conflicts with SEC1001.
    async with Client(server) as client:
        plan = await plan_schedules(BannerTools(client), "S10001", TERM, ["CIS376", "CIS410"])
    assert [o["section_ids"] for o in plan.options] == [["SEC1001", "SEC2002"]]
    assert plan.options[0]["total_credit_hours"] == 6
    assert plan.rejection_counts == {"TIME_CONFLICT": 1}


async def test_plan_excludes_course_with_missing_prerequisites():
    async with Client(server) as client:
        plan = await plan_schedules(BannerTools(client), "S10001", TERM, ["CIS450", "CIS410"])
    assert codes(plan) == {"CIS450": "MISSING_PREREQUISITE"}
    assert all("SEC3001" not in o["section_ids"] for o in plan.options)


async def test_plan_respects_earliest_start_preference():
    # SEC1001 starts 09:30, so CIS376 has no section at or after 10:00.
    async with Client(server) as client:
        plan = await plan_schedules(
            BannerTools(client), "S10001", TERM, ["CIS376", "CIS410"],
            Preferences(earliest_start="10:00"),
        )
    assert codes(plan) == {"CIS376": "NO_SECTION_MATCHES_PREFERENCES"}
    assert sorted(o["section_ids"][0] for o in plan.options) == ["SEC2001", "SEC2002"]


async def test_plan_reports_unknown_and_unoffered_courses():
    async with Client(server) as client:
        plan = await plan_schedules(BannerTools(client), "S10001", TERM, ["XYZ999", "CIS330"])
    assert codes(plan) == {"XYZ999": "UNKNOWN_COURSE", "CIS330": "NO_SECTIONS_IN_TERM"}
    assert plan.options == []


async def test_every_option_passes_the_validator(ds):
    from scheduling.validators import validate_schedule

    async with Client(server) as client:
        plan = await plan_schedules(BannerTools(client), "S10001", TERM, ["CIS376", "CIS410"])
    for option in plan.options:
        check = validate_schedule(
            ds.students["S10001"], option["section_ids"], TERM, ds.sections, ds.courses
        )
        assert check.valid, check.to_dict()


# ---------------------------------------------------------------- real transport


async def test_stdio_end_to_end():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with Client(params) as client:
        plan = await plan_schedules(BannerTools(client), "S10001", TERM, ["CIS376", "CIS410"])
    assert [o["section_ids"] for o in plan.options] == [["SEC1001", "SEC2002"]]
