"""Offline security tests for Microsoft Entra JWT verification.

Uses synthetic identities and local RSA signing keys.
No Microsoft account, credentials, or network access required.
"""

import asyncio
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.mcp_server.entra_token_verifier import EntraTokenVerifier


TENANT = "11111111-1111-4111-8111-111111111111"
AUDIENCE = "22222222-2222-4222-8222-222222222222"
CLIENT = "33333333-3333-4333-8333-333333333333"
USER = "44444444-4444-4444-8444-444444444444"


@pytest.fixture
def token_setup(monkeypatch):
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    verifier = EntraTokenVerifier(
        tenant_id=TENANT,
        audience=AUDIENCE,
    )

    # Trust only the local test key. No Microsoft network request.
    monkeypatch.setattr(
        verifier._jwks_client,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=key.public_key()),
    )

    def make_token(**overrides):
        now = int(time.time())
        claims = {
            "iss": verifier.issuer,
            "aud": AUDIENCE,
            "tid": TENANT,
            "oid": USER,
            "azp": CLIENT,
            "scp": "academic.read",
            "ver": "2.0",
            "iat": now,
            "nbf": now,
            "exp": now + 1800,
        }
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256")

    return verifier, key, make_token


def verify(verifier, token):
    return asyncio.run(verifier.verify_token(token))


def test_valid_signed_token_accepted(token_setup):
    verifier, _, make_token = token_setup

    result = verify(verifier, make_token())

    assert result is not None
    assert result.claims["oid"] == USER
    assert "academic.read" in result.scopes


def test_token_signed_with_untrusted_key_rejected(token_setup):
    verifier, _, make_token = token_setup

    another_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    now = int(time.time())
    forged = jwt.encode(
        {
            "iss": verifier.issuer,
            "aud": AUDIENCE,
            "tid": TENANT,
            "oid": USER,
            "azp": CLIENT,
            "scp": "academic.read",
            "ver": "2.0",
            "iat": now,
            "nbf": now,
            "exp": now + 1800,
        },
        another_key,
        algorithm="RS256",
    )

    assert verify(verifier, forged) is None


@pytest.mark.parametrize(
    "claim,value",
    [
        ("aud", "99999999-9999-4999-8999-999999999999"),
        ("tid", "99999999-9999-4999-8999-999999999999"),
        ("iss", "https://untrusted.invalid"),
        ("scp", "other.permission"),
        ("ver", "1.0"),
        ("oid", ""),
        ("azp", ""),
    ],
)
def test_invalid_claim_rejected(token_setup, claim, value):
    verifier, _, make_token = token_setup

    token = make_token(**{claim: value})

    assert verify(verifier, token) is None


def test_expired_token_rejected(token_setup):
    verifier, _, make_token = token_setup

    token = make_token(exp=int(time.time()) - 300)

    assert verify(verifier, token) is None


def test_future_token_rejected(token_setup):
    verifier, _, make_token = token_setup

    token = make_token(nbf=int(time.time()) + 300)

    assert verify(verifier, token) is None


@pytest.mark.parametrize(
    "token",
    ["", "not-a-jwt", "x" * 16385],
    ids=["empty", "malformed", "oversized"],
)
def test_malformed_token_rejected(token_setup, token):
    verifier, _, _ = token_setup

    assert verify(verifier, token) is None
