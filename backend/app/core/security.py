"""Verifies the access tokens (JWTs) that Supabase Auth gives the frontend.

Supabase signs tokens either with asymmetric signing keys (ES256/RS256, public keys at the
project's JWKS endpoint) or, on older projects, with one shared secret (HS256). Both are accepted;
the key is chosen by the token's algorithm, so a token can never be checked against the wrong kind
of key.
"""
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import jwt

AUDIENCE = "authenticated"
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
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class SupabaseTokenVerifier:
    def __init__(
        self,
        supabase_url: str,
        jwt_secret: str | None = None,
        jwks_client: SigningKeySource | None = None,
    ) -> None:
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self._jwt_secret = jwt_secret
        # PyJWKClient caches the keys and refetches when it sees an unknown key id.
        self._jwks_client = jwks_client or jwt.PyJWKClient(f"{self.issuer}/.well-known/jwks.json")

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
            if algorithm in ASYMMETRIC_ALGORITHMS:
                key = self._jwks_client.get_signing_key_from_jwt(token).key
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
