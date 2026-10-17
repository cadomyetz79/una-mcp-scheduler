import sys
from pathlib import Path

import pytest

# Make "scheduling" importable (the folder name "ai-agent" has a hyphen,
# so it cannot be a Python package itself).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scheduling.loader import load_dataset  # noqa: E402


@pytest.fixture(scope="session")
def ds():
    return load_dataset()


@pytest.fixture
def anyio_backend():
    # Async tests run on asyncio (the anyio pytest plugin ships with mcp).
    return "asyncio"
