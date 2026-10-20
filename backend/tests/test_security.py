import base64
import json
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

    def test_small_clock_difference_is_accepted(self) -> None:
        # Right after sign-up the token is brand new; Supabase's clock may be a little ahead.
        token = make_token(self.key, issued_in=30)

        self.assertEqual("student@example.com", self.verifier.verify(token).email)

    def test_signing_keys_are_fetched_with_certifi_bundle(self) -> None:
        # Works even where Python has no CA certificates of its own.
        verifier = SupabaseTokenVerifier(SUPABASE_URL)
        context = verifier._jwks_client.ssl_context

        self.assertIsNotNone(context)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_issuer_is_built_from_project_url(self) -> None:
        verifier = SupabaseTokenVerifier(SUPABASE_URL + "/", jwks_client=FakeJwks(self.key))
        self.assertEqual(ISSUER, verifier.issuer)

    def test_rejects_bad_tokens(self) -> None:
        other_key = new_signing_key()
        cases = {
            "expired": make_token(self.key, expires_in=-3600),
            "issued far in the future": make_token(self.key, issued_in=300, expires_in=3900),
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

    def test_header_algorithm_must_match_signing_key(self) -> None:
        # An RS256 header pointing at the project's EC key used to crash PyJWT (TypeError → 500).
        header, payload, signature = make_token(self.key).split(".")
        forged_header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
            .rstrip(b"=")
            .decode()
        )

        with self.assertRaises(AuthError):
            self.verifier.verify(f"{forged_header}.{payload}.{signature}")

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
