"""Second held-out set (evaluation/heldout2/): shape, independence, oracles.

Oracles replay each case's ideal tool calls through the real assistant (all
checks on), planner and MCP server on the set's own data, and are scored with
scoring v2. This validates the expectations against the deterministic
system; it says nothing about a model.
"""

import json
import re

import pytest

import dev.fake_mcp_server as fake
from agent.llm import ScriptedLLM
from evaluation.run_eval import data_dir_of, load_cases, run_case
from evaluation.scoring import score_case_v2
from scheduling.loader import load_dataset

pytestmark = pytest.mark.anyio

H2 = load_cases(dataset="heldout2")
DS2 = load_dataset(data_dir_of(H2))
OTHERS = {name: load_cases(dataset=name) for name in ("dev", "heldout", "security")}
CORPUS = json.loads((data_dir_of(H2).parents[1] / "security" / "corpus.json").read_text(encoding="utf-8"))

GENERIC = set("""a an and the i me my for to of in on at it is be can could would please next spring term
semester plan schedule take want like class classes course courses section sections""".split())


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - GENERIC


def test_shape_and_coverage():
    cases = H2["cases"]
    assert len(cases) == 37 and len({c["id"] for c in cases}) == 37
    assert H2["scoring_version"] == 2
    cats = {c["category"] for c in cases}
    for needed in ("plan_two_courses", "mandatory_preference", "soft_preference", "mixed_preferences",
                   "relaxed_preference", "prerequisite", "availability", "full_section", "named_sections_conflict",
                   "section_ids_only", "credit_limit", "inactive_student", "corequisite", "clarification",
                   "privacy", "override_attack", "exfiltration_attack", "forged_tool_output_attack",
                   "dictated_reply", "indirect_injection_in_data", "impersonation"):
        assert needed in cats, needed


def test_requests_are_not_copies_of_any_earlier_request():
    earlier = [c["request"] for d in OTHERS.values() for c in d["cases"]]
    earlier += [c["text"] for group in ("attacks", "legitimate") for c in CORPUS[group]]
    earlier_words = [words(t) for t in earlier]
    for c in H2["cases"]:
        w = words(c["request"])
        assert c["request"] not in earlier
        closest = max(len(w & e) / max(1, len(w | e)) for e in earlier_words)
        assert closest < 0.5, (c["id"], closest)


def test_own_data_only():
    """Courses, sections and students the cases rely on exist only in this set's data."""
    others = set()
    for d in OTHERS.values():
        others |= set(load_dataset(data_dir_of(d)).sections)
    new_sections = set(DS2.sections) - set(load_dataset().sections)
    assert new_sections and not (new_sections & others)
    assert all(c["student_id"].startswith("S3") for c in H2["cases"])


@pytest.fixture
def heldout2_server(monkeypatch):
    monkeypatch.setattr(fake, "DATA_DIR", data_dir_of(H2))
    return fake.server


@pytest.mark.parametrize("case_id", [c["id"] for c in H2["cases"]])
async def test_oracle(case_id, heldout2_server):
    case = next(c for c in H2["cases"] if c["id"] == case_id)
    record = await run_case(case, H2["term_id"], ScriptedLLM(case["oracle"]), heldout2_server)
    score = score_case_v2(case, record, DS2)
    assert score["pass"], score["checks"]
