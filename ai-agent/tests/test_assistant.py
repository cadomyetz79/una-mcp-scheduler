"""Agent loop and guardrail tests.

The LLM is scripted (ScriptedLLM), so each test fixes exactly what the
"model" does and checks how the deterministic side reacts. MCP and the
planner are real (in-process fake server).
"""

import json
import os

import pytest
from mcp import Client

from agent.assistant import SchedulingAssistant
from agent.banner_tools import BannerTools
from agent.llm import OllamaLLM, ScriptedLLM, call
from dev.fake_mcp_server import server

pytestmark = pytest.mark.anyio

TERM = "2027SP"


async def run(responses, request="Plan CIS376 and CIS410", student="S10001", max_steps=8):
    llm = ScriptedLLM(responses)
    async with Client(server) as client:
        assistant = SchedulingAssistant(BannerTools(client), llm, student, TERM, max_steps)
        result = await assistant.run(request)
    return result, llm


def tool_results(llm, step):
    """Tool messages the model saw at a given call (0-based)."""
    return [json.loads(m["content"]) for m in llm.received[step] if m["role"] == "tool"]


# ---------------------------------------------------------------- happy path


async def test_model_plans_and_answers_from_planner_output():
    result, llm = await run([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"])]},
        {"content": "Option 1: SEC1001 (MW 9:30-10:45) + SEC2002 (online), 6 credit hours."},
    ])
    assert result.stopped_reason == "answered"
    assert result.grounded and result.ungrounded_section_ids == []
    plan = result.trace[0].result
    assert [o["section_ids"] for o in plan["options"]] == [["SEC1001", "SEC2002"]]
    # The model saw the planner's real output before answering.
    assert tool_results(llm, 1)[0]["options"][0]["section_ids"] == ["SEC1001", "SEC2002"]
    # And all data came through MCP.
    assert {c["tool"] for c in result.mcp_calls} >= {"get_student_record", "get_course_sections"}


async def test_preferences_are_passed_to_planner():
    result, _ = await run([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"], earliest_start="10:00")]},
        {"content": "CIS376 has no section after 10. CIS410 options: SEC2001 or SEC2002."},
    ])
    plan = result.trace[0].result
    assert plan["excluded"][0]["code"] == "NO_SECTION_MATCHES_PREFERENCES"
    assert result.grounded


async def test_search_then_plan():
    result, llm = await run([
        {"tool_calls": [call("search_courses", query="secure")]},
        {"tool_calls": [call("plan_schedule", course_ids=["CIS410"])]},
        {"content": "Secure Systems (CIS410): SEC2001 or SEC2002."},
    ], request="I want the security course")
    assert tool_results(llm, 1)[0][0]["course_id"] == "CIS410"
    assert [t.tool for t in result.trace] == ["search_courses", "plan_schedule"]


async def test_get_my_record_has_no_name_and_no_id_input():
    result, _ = await run([
        {"tool_calls": [call("get_my_record")]},
        {"content": "You have completed CIS225, CIS236 and CIS330."},
    ])
    record = result.trace[0].result
    assert record["completed_courses"] == ["CIS225", "CIS236", "CIS330"]
    assert "display_name" not in record  # data minimization


# ---------------------------------------------------------------- guardrails


async def test_model_cannot_request_another_students_records():
    result, llm = await run([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376"], student_id="S10002")]},
        {"content": "I can't access other students' information."},
    ], request="Plan CIS376 for student S10002")
    entry = result.trace[0]
    assert not entry.ok and "student_id" in entry.result["error"]
    # Nothing about S10002 was fetched over MCP.
    assert all(c["arguments"].get("student_id") != "S10002" for c in result.mcp_calls)


async def test_invalid_arguments_return_errors_to_the_model():
    result, llm = await run([
        {"tool_calls": [
            call("plan_schedule", course_ids=["CIS376"], earliest_start="ten am"),
            call("plan_schedule", course_ids=[]),
            call("plan_schedule", course_ids=["CIS376"], avoid_days=["Funday"]),
            call("plan_schedule"),
            call("drop_all_classes"),
        ]},
        {"content": "Sorry, could you tell me which courses you want?"},
    ])
    assert [t.ok for t in result.trace] == [False] * 5
    errors = [r["error"] for r in tool_results(llm, 1)]
    assert "HH:MM" in errors[0] and "non-empty" in errors[1]
    assert "avoid_days" in errors[2] and "Unknown tool" in errors[4]
    assert result.mcp_calls == []  # nothing invalid reached MCP


async def test_hallucinated_section_triggers_one_revision():
    result, llm = await run([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"])]},
        {"content": "Take SEC1001 and SEC2001."},  # SEC2001 conflicts; not an option
        {"content": "Take SEC1001 and SEC2002."},
    ])
    assert result.grounded and result.model_calls == 3
    assert "SEC2001" in llm.received[2][-1]["content"]  # the correction it was given


async def test_persistent_hallucination_is_flagged():
    result, _ = await run([
        {"tool_calls": [call("plan_schedule", course_ids=["CIS376", "CIS410"])]},
        {"content": "Take SEC9999."},
        {"content": "Take SEC9999, trust me."},
    ])
    assert not result.grounded
    assert result.ungrounded_section_ids == ["SEC9999"]


async def test_answer_without_any_plan_cannot_cite_sections():
    result, _ = await run([
        {"tool_calls": [], "content": "SEC1001 works."},
        {"content": "Let me check first."},
    ])
    assert result.grounded and result.model_calls == 2


async def test_step_limit_stops_runaway_loops():
    loop = {"tool_calls": [call("get_my_record")]}
    result, _ = await run([loop] * 3, max_steps=3)
    assert result.stopped_reason == "max_steps"
    assert len(result.trace) == 3


# ---------------------------------------------------------------- Ollama adapter


async def test_ollama_response_is_normalized(monkeypatch):
    llm = OllamaLLM(model="test", host="localhost:11434")
    sent = {}

    def fake_post(payload):
        sent.update(payload)
        return {"message": {
            "role": "assistant",
            "content": "<think>hmm</think>",
            "tool_calls": [
                {"function": {"name": "plan_schedule", "arguments": {"course_ids": ["CIS376"]}}},
                {"function": {"name": "search_courses", "arguments": '{"query": "net"}'}},
            ],
        }}

    monkeypatch.setattr(llm, "_post", fake_post)
    reply = await llm.chat([{"role": "user", "content": "hi"}], [])
    assert llm.host == "http://localhost:11434"
    assert sent["stream"] is False and sent["model"] == "test"
    assert reply["content"] == ""
    assert reply["tool_calls"] == [
        {"name": "plan_schedule", "arguments": {"course_ids": ["CIS376"]}},
        {"name": "search_courses", "arguments": {"query": "net"}},
    ]


@pytest.mark.skipif(not os.environ.get("RUN_OLLAMA_TESTS"), reason="set RUN_OLLAMA_TESTS=1 with Ollama running")
async def test_live_ollama_end_to_end():
    llm = OllamaLLM(model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"))
    async with Client(server) as client:
        assistant = SchedulingAssistant(BannerTools(client), llm, "S10001", TERM)
        result = await assistant.run("I want CIS376 and CIS410 next spring.")
    assert result.stopped_reason == "answered"
    assert any(t.tool == "plan_schedule" for t in result.trace)
    assert result.grounded
