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


def make_pdf(pages: list[list[str]], link: str | None = None) -> bytes:
    """A minimal text-based PDF: one list of text lines per page, optional link on page 1."""

    def escape(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, lines in enumerate(pages):
        stream = "BT /F1 10 Tf 50 750 Td 12 TL " + " ".join(
            f"({escape(line)}) '" for line in lines
        ) + " ET"
        annots = ""
        if link and index == 0:
            annots = f" /Annots [<< /Type /Annot /Subtype /Link /Rect [50 700 300 720] /Border [0 0 0] /A << /S /URI /URI ({link}) >> >>]"
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[index] + 1} 0 R{annots} >>"
            ).encode()
        )
        data = stream.encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


RESUME_LINES = [
    "Ada Student",
    "ada@example.com | (608) 555-0100 | Madison, WI",
    "EDUCATION",
    "University of Wisconsin-Madison, B.S. Computer Science, 2023 - 2027, GPA 3.8",
    "EXPERIENCE",
    "Software Engineering Intern, Example Corp, Seattle, WA, Jun 2025 - Aug 2025",
    "- Built a FastAPI service used by three internal teams",
    "- Cut test runtime by 40 percent by parallelising the suite",
    "SKILLS",
    "Python, TypeScript, FastAPI, React, PostgreSQL, Docker, Git",
]
