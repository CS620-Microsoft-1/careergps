import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.schemas.action_plans import ActionPlanSuggestions
from app.services.action_plans.planner import get_action_planner
from app.services.plans import get_plan_store
from app.services.skill_gaps.runs import get_skill_gap_run_manager
from tests.test_action_plan_planner import run
from tests.test_skill_gap_authenticated_api import FakeAccounts, FakeVerifier, USER_ID

URL = "/action-plans/suggestions"
BODY = {"job_family": "software_engineer"}


class FakeRuns:
    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error = result, error

    def latest(self, **_kwargs):
        if self.error:
            raise self.error
        return self.result


class FakeStore:
    def __init__(self, items=(), error: Exception | None = None):
        self._items, self.error = list(items), error

    def items(self, user_id, family):
        if self.error:
            raise self.error
        return self._items


class FakePlanner:
    def __init__(self, events: list, error: Exception | None = None):
        self.events, self.error, self.calls = events, error, []

    def suggest(self, run, **kwargs):
        self.events.append("suggest")
        self.calls.append((run, kwargs))
        if on_event := kwargs.get("on_event"):
            on_event({"type": "stage", "stage": "gaps", "gaps": [{"skill_id": "sql", "skill_name": "SQL"}]})
            on_event({"type": "stage", "stage": "agent"})
        if self.error:
            raise self.error
        return ActionPlanSuggestions(job_family=run.job_family, skill_gap_run_id=run.id, mode=kwargs["mode"],
                                     source="rules", generated_at="2026-11-19T00:00:00+00:00", plans=[],
                                     uncovered_skill_ids=[])


class RecordingAccounts(FakeAccounts):
    def __init__(self, events: list):
        super().__init__()
        self.events = events
        self.user.university = "University of Wisconsin-Madison"

    def end_reads(self):
        self.events.append("end_reads")


class RouteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        self.accounts = RecordingAccounts(self.events)
        self.runs = FakeRuns(run())
        self.store = FakeStore([{"resource_id": "p_done", "status": "done"},
                                {"resource_id": "p_saved", "status": "saved"}])
        self.planner = FakePlanner(self.events)
        verifier = FakeVerifier({"owner-token": USER_ID})
        overrides = {deps.get_token_verifier: lambda: verifier, deps.get_account_service: lambda: self.accounts,
                     deps.get_db: lambda: None, get_skill_gap_run_manager: lambda: self.runs,
                     get_plan_store: lambda: self.store, get_action_planner: lambda: self.planner}
        app.dependency_overrides.update(overrides)
        self.addCleanup(app.dependency_overrides.clear)
        taken = patch("app.api.routes.action_plans.list_taken",
                      return_value=[SimpleNamespace(course_id="cs_400")])
        self.list_taken = taken.start()
        self.addCleanup(taken.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer owner-token"}

    def post(self, body=BODY):
        return self.client.post(URL, json=body, headers=self.headers)



class ActionPlanRouteTest(RouteTestCase):
    def test_requires_login(self) -> None:
        self.assertEqual(self.client.post(URL, json=BODY).status_code, 401)

    def test_passes_what_the_student_already_finished(self) -> None:
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["skill_gap_run_id"], run().id)
        [(called_run, options)] = self.planner.calls
        self.assertEqual(called_run.job_family, "software_engineer")
        self.assertEqual(options, {"mode": "full", "university": "University of Wisconsin-Madison",
                                   "taken_course_ids": {"cs_400"}, "done_resource_ids": {"p_done"}})

    def test_ends_the_read_transaction_before_the_agent(self) -> None:
        self.post()
        self.assertEqual(self.events[-2:], ["end_reads", "suggest"])

    def test_no_run_is_404(self) -> None:
        self.runs.error = KeyError("none")
        self.assertEqual(self.post().status_code, 404)

    def test_unfinished_or_failed_run_is_409(self) -> None:
        for status, text in (("running", "not finished"), ("failed", "failed")):
            with self.subTest(status):
                self.runs.result = run(status)
                response = self.post()
                self.assertEqual(response.status_code, 409)
                self.assertIn(text, response.json()["detail"])
        self.assertEqual(self.planner.calls, [])

    def test_storage_errors_are_503(self) -> None:
        self.store.error = OSError("disk")
        self.assertEqual(self.post().status_code, 503)
        self.store.error = None
        self.planner.error = OSError("disk")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Action plans are unavailable")

    def test_request_is_strict(self) -> None:
        for body in ({**BODY, "mode": "skill"}, {**BODY, "extra": 1}, {"job_family": "astronaut"}):
            with self.subTest(body):
                self.assertEqual(self.post(body).status_code, 422)



class ActionPlanStreamRouteTest(RouteTestCase):
    STREAM = URL + "/stream"

    def stream(self, body=BODY):
        return self.client.post(self.STREAM, json=body, headers=self.headers)

    @staticmethod
    def lines(response) -> list[dict]:
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_streams_each_stage_then_the_result(self) -> None:
        response = self.stream()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/x-ndjson")
        events = self.lines(response)
        self.assertEqual([event.get("stage", event["type"]) for event in events], ["gaps", "agent", "result"])
        self.assertEqual(events[-1]["suggestions"]["skill_gap_run_id"], run().id)
        options = self.planner.calls[0][1]
        self.assertEqual((options["taken_course_ids"], options["done_resource_ids"]), ({"cs_400"}, {"p_done"}))

    def test_run_problems_are_plain_http_errors_before_streaming(self) -> None:
        self.runs.result = run("running")
        self.assertEqual(self.stream().status_code, 409)
        self.runs.error = KeyError("none")
        self.assertEqual(self.stream().status_code, 404)
        self.assertEqual(self.planner.calls, [])

    def test_a_failure_after_streaming_starts_is_an_error_line(self) -> None:
        self.planner.error = OSError("disk")
        events = self.lines(self.stream())
        self.assertEqual(events[-1], {"type": "error", "status": 503, "detail": "Action plans are unavailable"})

    def test_an_unexpected_failure_logs_only_its_type(self) -> None:
        self.planner.error = RuntimeError("secret plan text")
        with self.assertLogs("app.api.routes.action_plans", "ERROR") as logs:
            events = self.lines(self.stream())
        self.assertEqual(events[-1]["status"], 500)
        self.assertNotIn("secret plan text", "".join(logs.output))

    def test_ends_the_read_transaction_before_the_agent(self) -> None:
        self.stream()
        self.assertEqual(self.events[-2:], ["end_reads", "suggest"])


if __name__ == "__main__":
    unittest.main()
