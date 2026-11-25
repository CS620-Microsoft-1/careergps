"""Agent call records: latency, tokens, cost, who made the call, and that every call site is covered."""
import threading
import unittest
import uuid
from decimal import Decimal
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.request_context import RequestContextMiddleware
from app.services import agent_calls
from app.services.model_prices import estimate_cost, price_for

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
RUN = uuid.UUID("22222222-2222-2222-2222-222222222222")


def response(**fields):
    usage = {"input_tokens": 12_000, "input_tokens_details": {"cached_tokens": 2_000},
             "output_tokens": 3_000, "output_tokens_details": {"reasoning_tokens": 1_000}}
    return SimpleNamespace(**{"model": "gpt-6-luna", "status": "completed", "usage": usage, **fields})


class FailingSink:
    def write(self, row):
        raise ConnectionError("database down")


class RecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sink = agent_calls.MemorySink()
        agent_calls.use_sink(self.sink)
        self.addCleanup(agent_calls.use_sink, agent_calls.MemorySink())

    def test_completed_call_records_tokens_and_cost(self) -> None:
        result = response()
        self.assertIs(result, agent_calls.call("resources-agent", "3", lambda **kwargs: result, input="x"))
        [row] = self.sink.rows
        self.assertEqual(("resources-agent", "3", "gpt-6-luna", "completed", None),
                         (row["agent"], row["agent_version"], row["model"], row["status"], row["error_type"]))
        self.assertEqual((12_000, 2_000, 3_000, 1_000), (row["input_tokens"], row["cached_tokens"],
                                                         row["output_tokens"], row["reasoning_tokens"]))
        # 10,000 uncached × $0.10 + 2,000 cached × $0.01 + 3,000 output × $0.50, per million tokens.
        self.assertEqual(Decimal("0.00252000"), row["cost_usd"])
        self.assertGreaterEqual(row["latency_ms"], 0)
        self.assertIsNone(row["user_id"])
        self.assertIsNone(row["run_id"])

    def test_passes_arguments_through(self) -> None:
        seen = {}
        agent_calls.call("a", None, lambda **kwargs: seen.update(kwargs) or response(), conversation="c", input=[1])
        self.assertEqual({"conversation": "c", "input": [1]}, seen)

    def test_error_is_reraised_and_recorded_by_type_only(self) -> None:
        def fail(**kwargs):
            raise RuntimeError("résumé text that must not be stored")

        with self.assertRaisesRegex(RuntimeError, "résumé text"):
            agent_calls.call("a", None, fail)
        [row] = self.sink.rows
        self.assertEqual(("error", "RuntimeError", None, None), (row["status"], row["error_type"], row["model"],
                                                                  row["cost_usd"]))
        self.assertNotIn("résumé", repr(row))

    def test_timeout_is_its_own_status(self) -> None:
        class APITimeoutError(Exception):
            pass

        def fail(**kwargs):
            raise APITimeoutError()

        with self.assertRaises(APITimeoutError):
            agent_calls.call("a", None, fail)
        self.assertEqual("timeout", self.sink.rows[0]["status"])

    def test_incomplete_response_keeps_its_status(self) -> None:
        agent_calls.call("a", None, lambda: response(status="incomplete"))
        self.assertEqual("incomplete", self.sink.rows[0]["status"])

    def test_missing_usage_leaves_tokens_and_cost_empty(self) -> None:
        agent_calls.call("a", None, lambda: SimpleNamespace(model="gpt-6-luna", status="completed"))
        row = self.sink.rows[0]
        self.assertEqual([None] * 5, [row[name] for name in ("input_tokens", "cached_tokens", "output_tokens",
                                                             "reasoning_tokens", "cost_usd")])

    def test_unknown_model_records_tokens_without_cost(self) -> None:
        with self.assertLogs("app.services.agent_calls", "WARNING"):
            agent_calls.call("a", None, lambda: response(model="some-new-model"))
        row = self.sink.rows[0]
        self.assertEqual((12_000, None), (row["input_tokens"], row["cost_usd"]))

    def test_dict_responses_are_read_too(self) -> None:
        agent_calls.call("a", None, lambda: vars(response()))
        self.assertEqual(3_000, self.sink.rows[0]["output_tokens"])

    def test_a_failed_write_never_changes_the_result(self) -> None:
        agent_calls.use_sink(FailingSink())
        result = response()
        with self.assertLogs("app.services.agent_calls", "WARNING") as logs:
            self.assertIs(result, agent_calls.call("a", None, lambda: result))
        self.assertNotIn("database down", "".join(logs.output))

    def test_a_failed_write_keeps_the_original_error(self) -> None:
        agent_calls.use_sink(FailingSink())

        def fail():
            raise ValueError("original")

        with self.assertLogs("app.services.agent_calls", "WARNING"), self.assertRaisesRegex(ValueError, "original"):
            agent_calls.call("a", None, fail)


class ContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sink = agent_calls.MemorySink()
        agent_calls.use_sink(self.sink)
        self.addCleanup(agent_calls.use_sink, agent_calls.MemorySink())

    def test_user_and_run_reach_a_worker_thread(self) -> None:
        token = agent_calls.start_request()
        self.addCleanup(agent_calls.end_request, token)
        agent_calls.set_user(str(USER))

        def work():
            with agent_calls.bind_run(RUN.hex):
                agent_calls.call("a", None, response)

        thread = threading.Thread(target=agent_calls.in_context(work))
        thread.start()
        thread.join()
        self.assertEqual((USER, RUN), (self.sink.rows[0]["user_id"], self.sink.rows[0]["run_id"]))

    def test_a_plain_thread_has_no_user(self) -> None:
        token = agent_calls.start_request()
        self.addCleanup(agent_calls.end_request, token)
        agent_calls.set_user(USER)
        thread = threading.Thread(target=lambda: agent_calls.call("a", None, response))
        thread.start()
        thread.join()
        self.assertIsNone(self.sink.rows[0]["user_id"])

    def test_set_user_outside_a_request_is_ignored(self) -> None:
        agent_calls.set_user(USER)
        agent_calls.call("a", None, response)
        self.assertIsNone(self.sink.rows[0]["user_id"])

    def test_a_sync_dependency_sets_the_user_for_the_endpoint(self) -> None:
        """FastAPI runs sync dependencies and endpoints in worker threads; the user must still arrive."""
        app = FastAPI()
        app.add_middleware(RequestContextMiddleware)

        def current_user():
            agent_calls.set_user(USER)

        @app.post("/run", dependencies=[Depends(current_user)])
        def run():
            thread = threading.Thread(target=agent_calls.in_context(lambda: agent_calls.call("a", None, response)))
            thread.start()
            thread.join()
            return {}

        @app.post("/anonymous")
        def anonymous():
            agent_calls.call("a", None, response)
            return {}

        with TestClient(app) as client:
            client.post("/run")
            client.post("/anonymous")
        self.assertEqual([USER, None], [row["user_id"] for row in self.sink.rows])


class PriceTests(unittest.TestCase):
    def test_dated_model_names_match_their_base_price(self) -> None:
        self.assertIs(price_for("gpt-6-luna"), price_for("gpt-6-luna-2026-09-22"))
        self.assertIsNone(price_for("gpt-6-lunar"))
        self.assertIsNone(price_for(None))

    def test_cached_tokens_never_exceed_input(self) -> None:
        self.assertEqual(Decimal("0.00001"), estimate_cost("gpt-6-luna", 1_000, 5_000, 0))


if __name__ == "__main__":
    unittest.main()
