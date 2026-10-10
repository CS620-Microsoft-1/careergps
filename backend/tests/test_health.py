import os
import sys
import unittest
from pathlib import Path

from sqlalchemy.exc import OperationalError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# CI has no .env. Creating the engine doesn't connect, so a dummy URL is enough;
# tests that need the database replace get_db with a fake session.
FAKE_PASSWORD = "not-a-real-password"
os.environ.setdefault(
    "DATABASE_URL", f"postgresql+psycopg://tester:{FAKE_PASSWORD}@localhost:5432/test"
)

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

FRONTEND_ORIGIN = "http://localhost:3000"


class FakeSession:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def execute(self, statement):
        if self.fail:
            raise OperationalError(
                "SELECT 1", {}, Exception(f"connection to tester:{FAKE_PASSWORD}@localhost failed")
            )
        return None


def use_session(session: FakeSession):
    def override():
        yield session

    return override


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health_returns_ok_without_database(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_health_db_returns_ok_when_database_responds(self) -> None:
        app.dependency_overrides[get_db] = use_session(FakeSession())

        response = self.client.get("/health/db")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok", "database": "connected"}, response.json())

    def test_health_db_returns_503_without_leaking_details(self) -> None:
        app.dependency_overrides[get_db] = use_session(FakeSession(fail=True))

        with self.assertLogs("app.api.routes.health", level="ERROR"):
            response = self.client.get("/health/db")

        self.assertEqual(503, response.status_code)
        self.assertEqual({"detail": "Database unreachable"}, response.json())
        self.assertNotIn(FAKE_PASSWORD, response.text)


class CorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def preflight(self, origin: str):
        return self.client.options(
            "/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    def test_frontend_origin_is_allowed(self) -> None:
        response = self.preflight(FRONTEND_ORIGIN)

        self.assertEqual(200, response.status_code)
        self.assertEqual(FRONTEND_ORIGIN, response.headers.get("access-control-allow-origin"))

    def test_unknown_origin_is_rejected(self) -> None:
        response = self.preflight("http://evil.example")

        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
