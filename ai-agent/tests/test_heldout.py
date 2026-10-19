"""Held-out evaluation set (evaluation/heldout/): shape, independence, oracle.

The oracle replays each case's ideal tool calls through the real assistant,
planner and MCP server (in-process, on the held-out data) and scores it with
scoring v2. This validates the expectations against the deterministic system;
it says nothing about a model.
"""

import re

import pytest

import dev.fake_mcp_server as fake
from agent.llm import ScriptedLLM
from evaluation.run_eval import data_dir_of, load_cases, run_case
from evaluation.scoring import score_case_v2
from scheduling.loader import load_dataset

pytestmark = pytest.mark.anyio

HELD = load_cases(dataset="heldout")
DEV = load_cases(dataset="dev")
HDS = load_dataset(data_dir_of(HELD))


# Generic scheduling words every request shares; similarity is measured on the rest.
GENERIC = set("""a an and the i me my for to of in on at it is be can could would please next spring term
semester plan schedule take want like class classes course courses section sections""".split())


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - GENERIC


def test_shape_and_coverage():
    cases = HELD["cases"]
    assert len(cases) >= 30 and len({c["id"] for c in cases}) == len(cases)
    assert HELD["scoring_version"] == 2
    cats = {c["category"] for c in cases}
    for needed in ("mixed_preferences", "negation", "conflicting_instructions", "prerequisite", "availability",
                   "time_conflict", "clarification", "invalid_arguments", "prompt_injection", "missing_mcp_data"):
        assert needed in cats, needed


def test_requests_are_not_copies_of_the_development_set():
    dev = [words(c["request"]) for c in DEV["cases"]]
    for c in HELD["cases"]:
        w = words(c["request"])
        closest = max(len(w & d) / len(w | d) for d in dev if w | d)
        assert closest < 0.5, (c["id"], closest)
        assert c["request"] not in {d["request"] for d in DEV["cases"]}


@pytest.fixture
def heldout_server(monkeypatch):
    monkeypatch.setattr(fake, "DATA_DIR", data_dir_of(HELD))
    return fake.server


@pytest.mark.parametrize("case_id", [c["id"] for c in HELD["cases"]])
async def test_oracle(case_id, heldout_server):
    case = next(c for c in HELD["cases"] if c["id"] == case_id)
    record = await run_case(case, HELD["term_id"], ScriptedLLM(case["oracle"]), heldout_server)
    score = score_case_v2(case, record, HDS)
    if case_id in HELD.get("touched_cases", {}):
        # Documented system limitation (see touched_cases): the deterministic
        # preference check overrides the student's relaxation in H32.
        assert not score["pass"]
        return
    assert score["pass"], score["checks"]


@pytest.mark.parametrize("case_id", [c["id"] for c in DEV["cases"]])
async def test_dev_oracle_under_scoring_v2(case_id):
    dev2 = load_cases(dataset="dev", scoring_version=2)
    case = next(c for c in dev2["cases"] if c["id"] == case_id)
    record = await run_case(case, dev2["term_id"], ScriptedLLM(case["oracle"]), fake.server)
    assert score_case_v2(case, record, load_dataset())["pass"]
