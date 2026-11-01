"""Microsoft Entra ID v2 access-token verification for MCP.

Single-tenant, delegated user tokens only.
No development bypasses and no real credentials stored here.
"""

import asyncio
from uuid import UUID

import jwt
from jwt import PyJWKClient

from mcp.server.auth.provider import AccessToken


class EntraTokenVerifier:
    def __init__(
        self,
        *,
        tenant_id: str,
        audience: str,
        required_scope: str = "academic.read",
    ):
        # Both values must be valid GUIDs.
        self.tenant_id = str(UUID(tenant_id))
        self.audience = str(UUID(audience))
        self.required_scope = required_scope

        self.issuer = (
            "https://login.microsoftonline.com/"
            f"{self.tenant_id}/v2.0"
        )

        # Fixed trusted Microsoft endpoint, never token-controlled.
        jwks_url = (
            "https://login.microsoftonline.com/"
            f"{self.tenant_id}/discovery/v2.0/keys"
        )

        self._jwks_client = PyJWKClient(
            jwks_url,
            timeout=5,
            cache_jwk_set=True,
            lifespan=300,
        )

    async def verify_token(
        self,
        token: str,
    ) -> AccessToken | None:
        """Return verified identity or reject the token."""

        if (
            not isinstance(token, str)
            or not token
            or len(token) > 16384
        ):
            return None

        try:
            # Avoid blocking the async MCP server during key retrieval.
            signing_key = await asyncio.to_thread(
                self._jwks_client.get_signing_key_from_jwt,
                token,
            )

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": [
                        "iss", "aud", "exp", "nbf", "iat",
                        "tid", "oid", "scp", "ver",
                    ],
                },
                leeway=30,
            )

        except Exception:
            # Invalid signatures, unavailable signing keys,
            # malformed tokens and expired tokens fail closed.
            return None

        if claims.get("ver") != "2.0":
            return None

        if claims.get("tid") != self.tenant_id:
            return None

        if claims.get("aud") != self.audience:
            return None

        object_id = claims.get("oid")
        client_id = claims.get("azp")
        scope_claim = claims.get("scp")

        if not isinstance(object_id, str) or not object_id:
            return None

        if not isinstance(client_id, str) or not client_id:
            return None

        if not isinstance(scope_claim, str):
            return None

        scopes = scope_claim.split()

        if self.required_scope not in scopes:
            return None

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=claims["exp"],
            resource=self.audience,
            subject=f"{self.tenant_id}:{object_id}",
            claims=claims,
        )
