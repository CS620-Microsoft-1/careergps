import sys
import unittest
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import jwt

from app.core.security import AuthError, AuthUnavailableError, SupabaseTokenVerifier
from tests.support import (
    ISSUER,
    LEGACY_SECRET,
    SUPABASE_URL,
    FakeJwks,
    make_token,
    new_signing_key,
)


class FailingJwks:
    def get_signing_key_from_jwt(self, token: str):
        raise jwt.PyJWKClientConnectionError("network down")


class SupabaseTokenVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = new_signing_key()
        self.verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(self.key))

    def test_valid_token_returns_user(self) -> None:
        user_id = uuid.uuid4()
        token = make_token(self.key, sub=str(user_id), email="  Student@Example.com ")

        user = self.verifier.verify(token)

        self.assertEqual(user_id, user.id)
        self.assertEqual("student@example.com", user.email)

    def test_issuer_is_built_from_project_url(self) -> None:
        verifier = SupabaseTokenVerifier(SUPABASE_URL + "/", jwks_client=FakeJwks(self.key))
        self.assertEqual(ISSUER, verifier.issuer)

    def test_rejects_bad_tokens(self) -> None:
        other_key = new_signing_key()
        cases = {
            "expired": make_token(self.key, expires_in=-60),
            "wrong audience": make_token(self.key, audience="anon"),
            "wrong issuer": make_token(self.key, issuer="https://other.supabase.co/auth/v1"),
            "signed by another key": make_token(other_key),
            "no email": make_token(self.key, email=None),
            "subject not a uuid": make_token(self.key, sub="not-a-uuid"),
            "not a jwt": "garbage",
            "unsigned": jwt.encode(
                {"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISSUER, "exp": 9999999999},
                None,
                algorithm="none",
            ),
        }
        for name, token in cases.items():
            with self.subTest(name), self.assertRaises(AuthError):
                self.verifier.verify(token)

    def test_legacy_secret_token_accepted_only_when_secret_configured(self) -> None:
        token = make_token(LEGACY_SECRET, algorithm="HS256")

        with self.assertRaises(AuthError):
            self.verifier.verify(token)

        legacy = SupabaseTokenVerifier(
            SUPABASE_URL, jwt_secret=LEGACY_SECRET, jwks_client=FakeJwks(self.key)
        )
        self.assertEqual("student@example.com", legacy.verify(token).email)

    def test_jwks_outage_is_not_reported_as_bad_token(self) -> None:
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FailingJwks())

        with self.assertRaises(AuthUnavailableError):
            verifier.verify(make_token(self.key))


if __name__ == "__main__":
    unittest.main()
