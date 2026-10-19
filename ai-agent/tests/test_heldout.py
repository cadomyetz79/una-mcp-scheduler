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
    # H32 failed here until 2026-10-19 (pre-registered limitation: the preference
    # check ignored the relaxation in the second sentence). The set is development
    # data since the security-hardening work, and relaxations are now handled.
    assert score["pass"], score["checks"]


def test_h32_relaxation_defers_to_the_model():
    from agent.preference_language import deferrals, reconcile

    request = next(c for c in HELD["cases"] if c["id"] == "H32")["request"]
    assert reconcile(request, ["avoid_days"], []) == ([], [])  # model said soft: unchanged
    assert reconcile(request, ["avoid_days"], ["avoid_days"]) == (["avoid_days"], [])  # no override either way
    (d,) = deferrals(request, ["avoid_days"], [])
    assert d["mandatory_cues"] == ["must"] and "no other way" in d["optional_cues"]


@pytest.mark.parametrize("case_id", [c["id"] for c in DEV["cases"]])
async def test_dev_oracle_under_scoring_v2(case_id):
    dev2 = load_cases(dataset="dev", scoring_version=2)
    case = next(c for c in dev2["cases"] if c["id"] == case_id)
    record = await run_case(case, dev2["term_id"], ScriptedLLM(case["oracle"]), fake.server)
    assert score_case_v2(case, record, load_dataset())["pass"]


def test_variability_overlays_retries_and_detects_flips(tmp_path):
    import json as _json

    from evaluation.variability import analyse

    def write(folder, cid, answer=None, error=None):
        folder.mkdir(exist_ok=True)
        rec = {"case_id": cid, "student_id": "S20002", "term_id": "2027SP", "request": ""}
        if error:
            rec["error"] = error
        else:
            rec["result"] = {"answer": answer, "grounded": True, "stopped_reason": "answered", "trace": [],
                             "mcp_calls": [], "recoveries": []}
        (folder / f"{cid}.json").write_text(_json.dumps({"record": rec}))

    data = {**HELD, "cases": [c for c in HELD["cases"] if c["id"] in ("H19", "H34")]}
    a, retry, b = tmp_path / "a", tmp_path / "retry", tmp_path / "b"
    write(a, "H19", error="TimeoutError: timed out")            # infra failure in run a ...
    write(retry, "H19", "I can only access your own record.")   # ... replaced by its retry
    write(a, "H34", "Which courses would you like?")
    write(b, "H19", "I can only access your own record.")
    write(b, "H34", "Here is your plan.")                        # no question: fails
    rows = {r["id"]: r for r in analyse(data, [[a, retry], [b]])}
    assert rows["H19"]["infrastructure_error"] == [False, False] and rows["H19"]["consistent"]
    assert rows["H34"]["pass"] == [True, False] and rows["H34"]["consistent"] is False
