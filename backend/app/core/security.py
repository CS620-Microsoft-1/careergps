"""Verifies the access tokens (JWTs) that Supabase Auth gives the frontend.

Supabase signs tokens either with asymmetric signing keys (ES256/RS256, public keys at the
project's JWKS endpoint) or, on older projects, with one shared secret (HS256). Both are accepted;
the key is chosen by the token's algorithm, so a token can never be checked against the wrong kind
of key.
"""
import ssl
import uuid
from dataclasses import dataclass
from typing import Protocol

import certifi
import jwt

AUDIENCE = "authenticated"
# Allowed clock difference between Supabase and this server. Without it, a token issued a second
# "in the future" by this machine's clock (a fresh token right after sign-up) would be rejected.
CLOCK_SKEW_SECONDS = 60
ASYMMETRIC_ALGORITHMS = {"ES256", "RS256"}


class AuthError(Exception):
    """The token is missing a claim, expired, or not signed by our Supabase project."""


class AuthUnavailableError(Exception):
    """The signing keys could not be fetched from Supabase."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


class SupabaseTokenVerifier:
    def __init__(
        self,
        supabase_url: str,
        jwt_secret: str | None = None,
        jwks_client: SigningKeySource | None = None,
    ) -> None:
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self._jwt_secret = jwt_secret
        # PyJWKClient caches the keys and refetches when it sees an unknown key id. certifi's CA
        # bundle, because some Pythons (python.org's on macOS) ship without CA certificates and
        # every key fetch would fail with 503.
        self._jwks_client = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            ssl_context=ssl.create_default_context(cafile=certifi.where()),
            timeout=10,
        )

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
            if algorithm in ASYMMETRIC_ALGORITHMS:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                # The header's alg is attacker-chosen: an RS256 header naming an EC key's kid would
                # otherwise crash PyJWT with a TypeError (500) instead of a 401.
                if signing_key.algorithm_name != algorithm:
                    raise AuthError(f"Token algorithm {algorithm} does not match its signing key")
                key = signing_key.key
            elif algorithm == "HS256" and self._jwt_secret:
                key = self._jwt_secret
            else:
                raise AuthError(f"Unsupported token algorithm: {algorithm}")

            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=AUDIENCE,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWKClientConnectionError as error:
            raise AuthUnavailableError("Could not fetch Supabase signing keys") from error
        except jwt.PyJWTError as error:
            raise AuthError(str(error)) from error

        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise AuthError("Token has no email")
        try:
            user_id = uuid.UUID(claims["sub"])
        except (ValueError, TypeError) as error:
            raise AuthError("Token subject is not a user id") from error

        return AuthenticatedUser(id=user_id, email=email.strip().lower())
