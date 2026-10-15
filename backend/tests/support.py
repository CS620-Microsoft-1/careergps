"""Helpers for tests that need Supabase-style login tokens. Not a test module itself."""
import time
import uuid
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
LEGACY_SECRET = "test-legacy-secret-that-is-at-least-32-bytes-long"


def new_signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


class FakeJwks:
    """Stands in for PyJWKClient: always returns the given key's public half."""

    def __init__(self, private_key: ec.EllipticCurvePrivateKey) -> None:
        self.public_key = private_key.public_key()

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self.public_key)


def make_token(
    key,
    *,
    algorithm: str = "ES256",
    sub: str | None = None,
    email: str | None = "student@example.com",
    audience: str = "authenticated",
    issuer: str = ISSUER,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    claims = {
        "sub": sub or str(uuid.uuid4()),
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in,
        "role": "authenticated",
    }
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, key, algorithm=algorithm)

