"""Account deletion through the Supabase Admin API. Fake DB session and HTTP transport; no network."""
import unittest
import uuid

import httpx2

from app.core.config import Settings
from app.services.account_deletion import (
    AccountDeletionFailed,
    AccountDeletionNotConfigured,
    delete_account,
)

SUPABASE_URL = "https://example-project.supabase.co"
SECRET = "sb_secret_test-only-not-a-real-key"


def _settings(**values) -> Settings:
    base = {"database_url": "postgresql+psycopg://x:y@localhost/z", "supabase_url": SUPABASE_URL,
            "supabase_service_role_key": SECRET}
    return Settings(_env_file=None, **{**base, **values})


class FakeSession:
    """Answers the one run-id query and records whether the read transaction was ended."""

    def __init__(self, run_ids: list[uuid.UUID]) -> None:
        self.run_ids = run_ids
        self.queries = 0
        self.rolled_back = False

    def scalars(self, _statement):
        self.queries += 1
        return iter(self.run_ids)

    def rollback(self) -> None:
        self.rolled_back = True


class AccountDeletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = uuid.uuid4()
        self.run_ids = [uuid.uuid4(), uuid.uuid4()]
        self.db = FakeSession(self.run_ids)
        self.requests: list[httpx2.Request] = []
        self.local_calls: list[tuple] = []

    def _client(self, status: int = 200, error: Exception | None = None) -> httpx2.Client:
        def handler(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            if error is not None:
                raise error
            return httpx2.Response(status, json={})
        return httpx2.Client(transport=httpx2.MockTransport(handler))

    def _delete_local(self, user_id, run_ids) -> None:
        self.local_calls.append((user_id, list(run_ids)))

    def _run(self, client: httpx2.Client, settings: Settings | None = None, **kwargs) -> None:
        delete_account(self.db, self.user_id, settings or _settings(), client=client,
                       delete_local=kwargs.get("delete_local", self._delete_local))

    def test_deletes_the_auth_user_then_local_files(self) -> None:
        self._run(self._client(200))

        self.assertEqual(1, len(self.requests))
        request = self.requests[0]
        self.assertEqual("DELETE", request.method)
        self.assertEqual(f"{SUPABASE_URL}/auth/v1/admin/users/{self.user_id}", str(request.url))
        self.assertEqual(SECRET, request.headers["apikey"])
        self.assertEqual(f"Bearer {SECRET}", request.headers["authorization"])
        self.assertTrue(self.db.rolled_back)
        self.assertEqual([(self.user_id, self.run_ids)], self.local_calls)

    def test_trailing_slash_in_supabase_url(self) -> None:
        self._run(self._client(200), _settings(supabase_url=SUPABASE_URL + "/"))
        self.assertEqual(f"{SUPABASE_URL}/auth/v1/admin/users/{self.user_id}", str(self.requests[0].url))

    def test_already_deleted_user_counts_as_success(self) -> None:
        self._run(self._client(404))
        self.assertEqual(1, len(self.local_calls))

    def test_supabase_error_changes_nothing(self) -> None:
        for status in (401, 403, 500, 503):
            with self.subTest(status=status):
                self.local_calls.clear()
                with self.assertRaises(AccountDeletionFailed) as caught:
                    self._run(self._client(status))
                self.assertIn(str(status), str(caught.exception))
                self.assertEqual([], self.local_calls)

    def test_network_error_changes_nothing_and_hides_the_key(self) -> None:
        with self.assertRaises(AccountDeletionFailed) as caught:
            self._run(self._client(error=httpx2.ConnectTimeout("timed out")))
        self.assertEqual([], self.local_calls)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_missing_configuration_makes_no_call(self) -> None:
        for values in ({"supabase_service_role_key": None}, {"supabase_service_role_key": ""},
                       {"supabase_url": None}):
            with self.subTest(values=values):
                with self.assertRaises(AccountDeletionNotConfigured):
                    self._run(self._client(200), _settings(**values))
        self.assertEqual([], self.requests)
        self.assertEqual(0, self.db.queries)
        self.assertEqual([], self.local_calls)

    def test_local_cleanup_failure_still_succeeds_and_warns(self) -> None:
        def broken(_user_id, _run_ids):
            raise OSError("disk error")

        with self.assertLogs("app.services.account_deletion", level="WARNING") as logs:
            self._run(self._client(200), delete_local=broken)
        self.assertTrue(any(str(self.user_id) in line for line in logs.output))
        self.assertFalse(any(SECRET in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
