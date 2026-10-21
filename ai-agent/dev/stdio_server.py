"""Launching the fake MCP server as a subprocess (stdio), with the right data.

Fix for R7 (quality pass 2026-10-20): the MCP SDK starts a stdio server with
only a few safe environment variables (HOME, PATH, ...), so UNA_DATA_DIR set
in the shell never reached the server, and dev/chat.py and dev/demo_plan.py
always used data/ without saying so. The data directory is now chosen
explicitly (--data-dir, else UNA_DATA_DIR, else data/), checked before the
server starts, and passed to the subprocess as its only extra variable (the
rest of the shell environment is not passed on).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.client.stdio import StdioServerParameters

SERVER = Path(__file__).resolve().with_name("fake_mcp_server.py")
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
# Files the fake server reads; enrollments.json is optional (without it the
# assistant reports that current registrations could not be checked).
REQUIRED_FILES = ("students.json", "course_history.json", "courses.json", "sections.json")


class DataDirError(ValueError):
    pass


def resolve_data_dir(cli_value: str | None = None, environ: dict | None = None) -> Path:
    """--data-dir if given, else UNA_DATA_DIR, else the repository's data/."""
    env = os.environ if environ is None else environ
    value = cli_value or env.get("UNA_DATA_DIR")
    path = Path(value).expanduser().resolve() if value else DEFAULT_DATA_DIR
    if not path.is_dir():
        raise DataDirError(f"data directory not found: {path}")
    missing = [name for name in REQUIRED_FILES if not (path / name).is_file()]
    if missing:
        raise DataDirError(f"data directory {path} is missing: {', '.join(missing)}")
    return path


def server_params(data_dir: Path) -> StdioServerParameters:
    """Parameters for Client(): the fake server reading data_dir."""
    return StdioServerParameters(command=sys.executable, args=[str(SERVER)],
                                 env={"UNA_DATA_DIR": str(data_dir)})
