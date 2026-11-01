"""Oversized request bodies are refused before the app (or login) reads them."""
import asyncio
import os
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test")

from fastapi.testclient import TestClient

from app.api import deps
from app.api.routes.resumes import MAX_UPLOAD_BYTES
from app.core.body_limit import BodyLimitMiddleware
from app.main import MAX_REQUEST_BYTES, app
from tests.test_skill_gap_authenticated_api import FakeVerifier

FRONTEND_ORIGIN = "http://localhost:3000"


def run(middleware, chunks, headers=()):
    """Call the middleware directly with a body sent in several http.request messages."""
    messages = [{"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
                for i, chunk in enumerate(chunks)]
    sent = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": list(headers)}
    asyncio.run(middleware(scope, receive, send))
    return sent


async def echo_length(scope, receive, send):
    """A tiny app that reads the whole body and answers with its length."""
    size, more = 0, True
    while more:
        message = await receive()
        size, more = size + len(message.get("body", b"")), message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(size).encode()})


class BodyLimitMiddlewareTests(unittest.TestCase):
    def test_streamed_body_over_the_limit_is_cut_off_with_413(self) -> None:
        sent = run(BodyLimitMiddleware(echo_length, max_bytes=10), [b"123456", b"78901"])

        self.assertEqual(413, sent[0]["status"])
        self.assertEqual(b'{"detail":"Request body is too large."}', sent[1]["body"])

    def test_declared_length_over_the_limit_is_refused_unread(self) -> None:
        sent = run(BodyLimitMiddleware(echo_length, max_bytes=10), [b"x"], headers=[(b"content-length", b"11")])

        self.assertEqual(413, sent[0]["status"])

    def test_body_within_the_limit_reaches_the_app(self) -> None:
        sent = run(BodyLimitMiddleware(echo_length, max_bytes=10), [b"12345", b"67890"])

        self.assertEqual(200, sent[0]["status"])
        self.assertEqual(b"10", sent[1]["body"])


class UploadLimitTests(unittest.TestCase):
    """POST /resumes/analyze parses the form before login runs; the limit must come first."""

    def setUp(self) -> None:
        app.dependency_overrides[deps.get_token_verifier] = lambda: FakeVerifier({})
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_limit_leaves_room_for_a_10_mb_resume(self) -> None:
        self.assertGreater(MAX_REQUEST_BYTES, MAX_UPLOAD_BYTES)
        self.assertLessEqual(MAX_REQUEST_BYTES, MAX_UPLOAD_BYTES + 2 * 1024 * 1024)

    def test_oversized_upload_is_413_with_cors_headers_before_login(self) -> None:
        response = self.client.post(
            "/resumes/analyze", headers={"Origin": FRONTEND_ORIGIN},
            files={"file": ("big.pdf", b"x" * (MAX_REQUEST_BYTES + 1), "application/pdf")},
        )

        self.assertEqual(413, response.status_code)
        self.assertEqual({"detail": "Request body is too large."}, response.json())
        self.assertEqual(FRONTEND_ORIGIN, response.headers.get("access-control-allow-origin"))

    def test_oversized_chunked_body_is_413(self) -> None:
        def body():
            for _ in range(12):
                yield b"x" * (1024 * 1024)

        response = self.client.post(
            "/resumes/analyze/stream", content=body(),
            headers={"Origin": FRONTEND_ORIGIN, "Content-Type": "multipart/form-data; boundary=b"},
        )

        self.assertEqual(413, response.status_code)
        self.assertEqual(FRONTEND_ORIGIN, response.headers.get("access-control-allow-origin"))

    def test_normal_upload_still_reaches_login(self) -> None:
        response = self.client.post("/resumes/analyze", files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")})

        self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
