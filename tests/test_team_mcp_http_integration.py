"""Real MCP HTTP protocol test with synthetic signed JWTs.

No live Entra tenant, external JWKS request, or real student data.
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx2
import jwt

from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "ai-agent"),
)
from agent.banner_tools import BannerTools
from agent.planner import plan_schedules
from agent.assistant import SchedulingAssistant
from agent.llm import ScriptedLLM, call

from src.mcp_server import team_security as security
from src.mcp_server import team_backend_client as backend
from src.mcp_server import team_protected_server as server



def read_payload(result):
    """Decode structured MCP results or JSON text results."""
    if result.structured_content is not None:
        payload = result.structured_content
    else:
        text = "".join(
            block.text
            for block in result.content
            if getattr(block, "type", None) == "text"
        )
        assert text, "MCP response has no readable content"
        payload = json.loads(text)

    if isinstance(payload, dict) and set(payload) == {"result"}:
        return payload["result"]

    return payload


TENANT = "11111111-1111-4111-8111-111111111111"
AUDIENCE = "22222222-2222-4222-8222-222222222222"
CLIENT_ID = "33333333-3333-4333-8333-333333333333"
USER_A = "44444444-4444-4444-8444-444444444444"
USER_B = "55555555-5555-4555-8555-555555555555"


def test_signed_identity_over_actual_mcp_http(monkeypatch):
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    verifier, issuer, check_resource = (
        security.select_auth_config(
            tenant_id=TENANT,
            audience=AUDIENCE,
        )
    )

    # The verifier trusts only this temporary local test key.
    # No Microsoft JWKS endpoint is contacted.
    monkeypatch.setattr(
        verifier._jwks_client,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(
            key=key.public_key()
        ),
    )

    monkeypatch.setattr(security, "ISSUER_URL", issuer)
    monkeypatch.setattr(
        security,
        "STUDENT_LOOKUP",
        {
            (TENANT, USER_A): "S10001",
            (TENANT, USER_B): "S10002",
        },
    )

    def sign_token(object_id):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": issuer,
                "aud": AUDIENCE,
                "tid": TENANT,
                "oid": object_id,
                "azp": CLIENT_ID,
                "scp": "academic.read",
                "ver": "2.0",
                "iat": now,
                "nbf": now,
                "exp": now + 1800,
            },
            key,
            algorithm="RS256",
            headers={"kid": "temporary-local-key"},
        )

    test_mcp = MCPServer(
        "UNA Team HTTP Integration Test",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer),
            resource_server_url=AnyHttpUrl(
                security.RESOURCE_URL
            ),
            required_scopes=["academic.read"],
            validate_token_resource=check_resource,
        ),
    )

    for handler in (
        server.get_student_record,
        server.get_course_history,
        server.get_course,
        server.search_courses,
        server.get_course_sections,
        server.get_student_enrollments,
    ):
        test_mcp.tool()(handler)

    app = test_mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    # Record which student IDs actually reach Mock Banner.
    backend_calls = []
    original_lookup = backend.get_student_record

    async def observed_lookup(student_id):
        backend_calls.append(student_id)
        return await original_lookup(student_id)

    monkeypatch.setattr(
        backend, "get_student_record", observed_lookup
    )

    async def check():
        transport = httpx2.ASGITransport(app=app)
        base_url = "http://127.0.0.1:8002"

        async with test_mcp.session_manager.run():
            async with httpx2.AsyncClient(
                transport=transport,
                base_url=base_url,
            ) as anonymous:
                reply = await anonymous.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                    },
                    headers={
                        "Accept": "application/json, text/event-stream",
                    },
                )
                assert reply.status_code == 401
                assert backend_calls == []

            for object_id, own_id, other_id in (
                (USER_A, "S10001", "S10002"),
                (USER_B, "S10002", "S10001"),
            ):
                async with httpx2.AsyncClient(
                    transport=transport,
                    base_url=base_url,
                    headers={
                        "Authorization": (
                            f"Bearer {sign_token(object_id)}"
                        ),
                    },
                ) as http_client:
                    async with Client(
                        streamable_http_client(
                            security.RESOURCE_URL,
                            http_client=http_client,
                        )
                    ) as client:
                        discovered = await client.list_tools()
                        names = {
                            tool.name for tool in discovered.tools
                        }
                        assert names == {
                            "get_student_record",
                            "get_course_history",
                            "get_course",
                            "search_courses",
                            "get_course_sections",
                            "get_student_enrollments",
                        }

                        own = await client.call_tool(
                            "get_student_record",
                            {"student_id": own_id},
                        )
                        assert own.is_error is False
                        assert (
                            read_payload(own)["student_id"]
                            == own_id
                        )

                        before = len(backend_calls)

                        denied = await client.call_tool(
                            "get_student_record",
                            {"student_id": other_id},
                        )
                        assert denied.is_error is True
                        assert read_payload(denied)["error_code"] == "FORBIDDEN"

                        # Cross-student access must be rejected
                        # before the backend is called.
                        assert len(backend_calls) == before

                        # Use the TEAM agent's actual MCP client.
                        tools = BannerTools(client)

                        student = await tools.student(own_id)
                        assert student.active is True

                        course = await tools.course("CIS410")
                        assert course.course_id == "CIS410"

                        matches = await tools.search_courses(
                            "secure", "CIS"
                        )
                        assert any(
                            row["course_id"] == "CIS410"
                            for row in matches
                        )

                        sections = await tools.sections(
                            "CIS410", "2027SP"
                        )
                        assert len(sections) == 2

                        enrolled = await tools.enrollments(
                            own_id, "2027SP"
                        )
                        assert enrolled is not None

                        expected = (
                            "SEC1001"
                            if own_id == "S10001"
                            else "SEC2002"
                        )
                        assert [
                            section.section_id
                            for section in enrolled
                        ] == [expected]

                        if own_id == "S10001":
                            plan = await plan_schedules(
                                tools,
                                own_id,
                                "2027SP",
                                ["CIS376", "CIS410"],
                            )
                            assert plan.current_registrations_checked
                            assert [
                                option["section_ids"]
                                for option in plan.options
                            ] == [["SEC1001", "SEC2002"]]

                            # Full TEAM conversational agent through
                            # authenticated MCP and team Mock Banner.
                            llm = ScriptedLLM([
                                {
                                    "tool_calls": [
                                        call(
                                            "plan_schedule",
                                            course_ids=["CIS376", "CIS410"],
                                        )
                                    ]
                                },
                                {
                                    "content": (
                                        "Option 1: SEC1001 and SEC2002, "
                                        "6 credit hours."
                                    )
                                },
                            ])

                            assistant = SchedulingAssistant(
                                BannerTools(client),
                                llm,
                                own_id,
                                "2027SP",
                            )
                            chat_result = await assistant.run(
                                "Plan CIS376 and CIS410"
                            )

                            assert chat_result.stopped_reason == "answered"
                            assert chat_result.grounded
                            assert "SEC1001" in chat_result.answer
                            assert "SEC2002" in chat_result.answer
                            assert any(
                                entry.tool == "plan_schedule"
                                and entry.ok
                                for entry in chat_result.trace
                            )
                            assert any(
                                entry["tool"] == "get_student_record"
                                for entry in chat_result.mcp_calls
                            )


        assert backend_calls == [
            "S10001", "S10001", "S10001", "S10001",
            "S10002", "S10002",
        ]

    asyncio.run(check())
