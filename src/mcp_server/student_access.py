"""Student-level authorization policy for the MCP server.

Only pass AccessToken instances obtained from trusted MCP authentication
middleware. This module does not parse or cryptographically verify JWTs.
Never construct access tokens from user prompts or agent tool arguments.
"""

from collections.abc import Mapping

from mcp.server.auth.provider import AccessToken


def resolve_authenticated_student_id(
    *,
    access_token: AccessToken | None,
    student_lookup: Mapping[tuple[str, str], str],
    allowed_issuer: str,
    required_scope: str = "academic.read",
) -> str:
    """Resolve the authorized student from a previously verified identity.

    The mapping key is (Entra tenant ID, Entra object ID), not an ID supplied
    by a chat message, LLM, or user-controlled MCP tool argument.
    """
    if access_token is None:
        raise PermissionError("Authentication required.")

    claims = access_token.claims

    if not isinstance(claims, dict):
        raise PermissionError("Verified identity claims required.")

    if not allowed_issuer or claims.get("iss") != allowed_issuer:
        raise PermissionError("Untrusted token issuer.")

    tenant_id = claims.get("tid")
    object_id = claims.get("oid")

    if (
        not isinstance(tenant_id, str)
        or not tenant_id.strip()
        or not isinstance(object_id, str)
        or not object_id.strip()
    ):
        raise PermissionError("Missing verified user identity.")

    if (
        not isinstance(access_token.scopes, (list, tuple, set))
        or required_scope not in access_token.scopes
    ):
        raise PermissionError("Insufficient academic permissions.")

    authorized_student = student_lookup.get((tenant_id, object_id))

    if (
        not isinstance(authorized_student, str)
        or not authorized_student.strip()
    ):
        raise PermissionError("No authorized student mapping.")

    return authorized_student


def require_student_read_access(
    *,
    access_token: AccessToken | None,
    student_id: str,
    student_lookup: Mapping[tuple[str, str], str],
    allowed_issuer: str,
    required_scope: str = "academic.read",
) -> str:
    """Authorize a request for one student's academic records.

    Identity resolution is trusted-server-side; requested student_id is
    compared against it. A tool argument cannot grant access by itself.
    """
    if access_token is None:
        raise PermissionError("Authentication required.")

    if not isinstance(student_id, str) or not student_id.strip():
        raise PermissionError("Invalid student ID.")

    authorized_student = resolve_authenticated_student_id(
        access_token=access_token,
        student_lookup=student_lookup,
        allowed_issuer=allowed_issuer,
        required_scope=required_scope,
    )

    if authorized_student != student_id:
        raise PermissionError(
            "Student is not authorized for these records."
        )

    return authorized_student
