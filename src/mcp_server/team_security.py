"""Authentication and student authorization for team MCP.

Requires verified MCP request context. No development
authentication bypass is enabled.
"""

import os

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier

from src.mcp_server.entra_token_verifier import EntraTokenVerifier
from src.mcp_server.student_access import require_student_read_access


RESOURCE_URL = "http://127.0.0.1:8002/mcp"
DEV_ISSUER_URL = "https://example.invalid/"


class RejectAllTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return None


def select_auth_config(
    *,
    tenant_id: str | None,
    audience: str | None,
) -> tuple[TokenVerifier, str, bool]:
    if bool(tenant_id) != bool(audience):
        raise ValueError(
            "Both UNA_ENTRA_TENANT_ID and "
            "UNA_ENTRA_API_CLIENT_ID are required."
        )

    if not tenant_id:
        return RejectAllTokenVerifier(), DEV_ISSUER_URL, True

    verifier = EntraTokenVerifier(
        tenant_id=tenant_id,
        audience=audience,
    )
    return verifier, verifier.issuer, False


TOKEN_VERIFIER, ISSUER_URL, VALIDATE_TOKEN_RESOURCE = (
    select_auth_config(
        tenant_id=os.getenv("UNA_ENTRA_TENANT_ID"),
        audience=os.getenv("UNA_ENTRA_API_CLIENT_ID"),
    )
)

# No production identity mappings are configured.
STUDENT_LOOKUP: dict[tuple[str, str], str] = {}


def authorize_student_request(student_id: str) -> str:
    return require_student_read_access(
        access_token=get_access_token(),
        student_id=student_id,
        student_lookup=STUDENT_LOOKUP,
        allowed_issuer=ISSUER_URL,
    )


def authorize_catalog_request() -> None:
    token = get_access_token()

    if token is None:
        raise PermissionError("Authentication required.")

    claims = token.claims
    if (
        not isinstance(claims, dict)
        or claims.get("iss") != ISSUER_URL
    ):
        raise PermissionError("Untrusted token issuer.")

    if "academic.read" not in token.scopes:
        raise PermissionError("Insufficient academic permissions.")

    if not all(
        isinstance(claims.get(name), str)
        and claims[name].strip()
        for name in ("tid", "oid")
    ):
        raise PermissionError("Missing verified user identity.")
