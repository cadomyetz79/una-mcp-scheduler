"""Launch the team's protected MCP service on localhost.

No student identity mappings are configured by default.
Without Entra configuration, all bearer tokens are rejected.
"""

from src.mcp_server.team_protected_server import mcp


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8002,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
