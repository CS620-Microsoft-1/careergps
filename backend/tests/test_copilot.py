"""Offline contract, authentication and bounded-tool-loop tests; no Azure calls or database."""
import json
import os
import unittest
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:fake@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_token_verifier
from app.api.routes.copilot import get_copilot_service, router
from app.core.config import CopilotSettings
from app.core.security import AuthenticatedUser, AuthError
from app.schemas.copilot import CopilotReply, CopilotRequest, SuggestionArguments
from app.services.copilot.agent import (
    CopilotError, FoundryCopilotService, agent_definition, matches_contract, run_orchestrator,
)
from app.services.copilot.tools import MockCopilotTools, ToolContext

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def call(name="get_skill_gap_analysis", args=None, call_id="call-1"):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args or {"skill_id": "sql"})}


def response(*calls, intent="explain_gap", sources=None, text="The sample resume has no explicit SQL evidence.", status="completed"):
    return SimpleNamespace(status=status, output=[Mock(model_dump=Mock(return_value=item)) for item in calls],
        output_text=json.dumps({"intent": intent, "text": text,
                                "source_ids": ["sample-report-sql"] if sources is None else sources}))


class CopilotTests(unittest.TestCase):
    def setUp(self):
        self.tools = MockCopilotTools(ToolContext(USER_ID))
        self.client = SimpleNamespace(responses=Mock())

    def run_chat(self, *responses, request=None, deadline=None):
        self.client.responses.create.side_effect = responses
        return run_orchestrator(self.client, {"type": "agent_reference", "name": "test", "version": "1"},
            request or CopilotRequest(question="Why SQL?"), self.tools,
            deadline=deadline if deadline is not None else monotonic() + 60)

    def test_gap_sources_come_from_tool_results(self):
        reply = self.run_chat(response(call()), response())
        self.assertEqual(reply.mode, "foundry_mock")
        self.assertEqual(reply.sources[0].id, "sample-report-sql")
        self.assertIn("does not prove", reply.sources[0].excerpt)
        for invocation in self.client.responses.create.call_args_list:
            self.assertFalse(invocation.kwargs["store"])
            self.assertNotIn("conversation", invocation.kwargs)
            self.assertNotIn("previous_response_id", invocation.kwargs)

    def test_tool_log_contains_only_name_status_and_elapsed_time(self):
        request = CopilotRequest(question="private-question-marker",
            history=[{"role": "user", "text": "private-history-marker"}])
        with self.assertLogs("uvicorn.error.copilot.tools", level="INFO") as captured:
            reply = self.run_chat(response(call()), response(), request=request)
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertRegex(record.getMessage(),
            r"^Copilot tool=get_skill_gap_analysis status=ok duration_ms=\d+\.\d{2}$")
        self.assertIsNone(record.exc_info)
        logged = repr(record.__dict__)
        for private in [request.question, request.history[0].text, str(USER_ID),
                        reply.text, reply.sources[0].excerpt, '"skill_id"']:
            self.assertNotIn(private, logged)

    def test_invalid_tool_arguments_and_unknown_names_are_not_logged(self):
        for tool_call, expected in [
            (call(args={"skill_id": "private-argument-marker"}), "get_skill_gap_analysis status=invalid_arguments"),
            (call(name="private-name-marker\nforged-log"), "unregistered status=unsupported_tool"),
        ]:
            with self.subTest(expected=expected), self.assertLogs("uvicorn.error.copilot.tools", level="INFO") as captured:
                self.run_chat(response(tool_call), response(intent="tool_error", sources=[], text="Unavailable"))
            self.assertEqual(len(captured.records), 1)
            self.assertIn(expected, captured.records[0].getMessage())
            self.assertNotIn("private-", repr(captured.records[0].__dict__))
            self.assertNotIn("forged-log", repr(captured.records[0].__dict__))

    def test_tool_exception_logs_status_without_exception_details(self):
        with patch.object(self.tools, "dispatch", side_effect=RuntimeError("private-exception-marker")):
            with self.assertLogs("uvicorn.error.copilot.tools", level="INFO") as captured:
                with self.assertRaises(RuntimeError):
                    self.run_chat(response(call()))
        self.assertEqual(len(captured.records), 1)
        self.assertRegex(captured.records[0].getMessage(),
            r"^Copilot tool=get_skill_gap_analysis status=error duration_ms=\d+\.\d{2}$")
        self.assertNotIn("private-exception-marker", repr(captured.records[0].__dict__))
        self.assertIsNone(captured.records[0].exc_info)

    def test_only_skill_gap_tool_is_registered_and_dispatchable(self):
        definition = agent_definition("test-model")
        self.assertEqual([tool["name"] for tool in definition["tools"]], ["get_skill_gap_analysis"])
        self.tools.dispatch("get_skill_gap_analysis", '{"skill_id":"sql"}')
        result = self.tools.dispatch("get_learning_suggestions", '{"skill_id":"sql","available_hours":8}')
        self.assertEqual(result.status, "unsupported_tool")
        self.assertEqual(result.sources, [])

    def test_unregistered_learning_call_cannot_supply_evidence(self):
        with self.assertRaises(CopilotError):
            self.run_chat(response(call()), response(call("get_learning_suggestions",
                {"skill_id": "sql", "available_hours": 8}, "call-2")),
                response(intent="learning_advice", sources=["sample-report-sql", "sample-suggestion-sql"]))

    def test_follow_up_history_is_untrusted_input_and_not_identity(self):
        request = CopilotRequest(question="What next?", history=[{"role": "assistant", "text": "Old sample answer"}])
        self.run_chat(response(intent="clarify", sources=[], text="Which skill?"), request=request)
        sent = self.client.responses.create.call_args.kwargs["input"]
        self.assertEqual(sent[0]["role"], "user")
        self.assertEqual(json.loads(sent[0]["content"])["history"], request.model_dump()["history"])
        self.assertNotIn(str(USER_ID), sent[0]["content"])

    def test_unknown_sources_or_missing_tools_are_rejected(self):
        for final in [response(sources=["invented"]), response(), response(intent="learning_advice")]:
            with self.subTest(final=final.output_text), self.assertRaises(CopilotError):
                self.run_chat(final)

    def test_learning_requires_both_evidence_types(self):
        with self.assertRaises(CopilotError):
            self.run_chat(response(call()), response(intent="learning_advice"))

    def test_unsupported_action_never_claims_execution(self):
        reply = self.run_chat(response(intent="unsupported_action", sources=[], text="I saved your plan."))
        self.assertIn("No changes were made", reply.text)
        self.assertNotIn("I saved", reply.text)

    def test_dispatch_blocks_unknown_tools_identity_and_bad_arguments(self):
        cases = [("delete_profile", "{}"), ("get_skill_gap_analysis", '{"skill_id":"sql","user_id":"other"}'),
                 ("get_skill_gap_analysis", '{"skill_id":"unknown"}'), ("get_skill_gap_analysis", "invalid")]
        for name, args in cases:
            with self.subTest(name=name, args=args):
                self.assertNotEqual(self.tools.dispatch(name, args).status, "ok")

    def test_reserved_suggestion_fixture_requires_analysis_and_respects_budget(self):
        args = SuggestionArguments(skill_id="sql", available_hours=2)
        self.assertEqual(self.tools.get_learning_suggestions(args).status, "invalid_arguments")
        self.tools.dispatch("get_skill_gap_analysis", '{"skill_id":"sql"}')
        result = self.tools.get_learning_suggestions(args)
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.sources, [])

    def test_tool_failure_is_returned_as_data(self):
        self.run_chat(response(call("unknown")), response(intent="tool_error", sources=[], text="That tool is unavailable."))
        inputs = self.client.responses.create.call_args.kwargs["input"]
        self.assertEqual(json.loads(inputs[-1]["output"])["status"], "unsupported_tool")

    def test_repeated_calls_round_limit_and_deadline(self):
        with self.assertRaises(CopilotError):
            self.run_chat(response(call()), response(call()))
        with self.assertRaises(CopilotError):
            self.run_chat(*(response(call(call_id=str(index))) for index in range(4)))
        self.client.responses.reset_mock()
        with self.assertRaises(CopilotError) as caught:
            self.run_chat(response(), deadline=monotonic() - 1)
        self.assertEqual(caught.exception.status_code, 504)
        self.client.responses.create.assert_not_called()

    def test_malformed_and_incomplete_answers_fail(self):
        for value in [SimpleNamespace(status="completed", output=[], output_text="not JSON"), response(status="incomplete")]:
            with self.subTest(value=value), self.assertRaises(CopilotError):
                self.run_chat(value)

    def test_contract_drift_is_detected(self):
        definition = agent_definition("test-model")
        self.assertTrue(matches_contract(definition))
        definition["tools" ] = []
        self.assertFalse(matches_contract(definition))

    def test_missing_configuration_never_calls_azure(self):
        service = FoundryCopilotService(CopilotSettings(_env_file=None))
        with self.assertRaises(CopilotError) as caught:
            service.chat(CopilotRequest(question="Hi"), ToolContext(USER_ID))
        self.assertEqual(caught.exception.status_code, 503)

    def test_context_bounds_and_role_restrictions(self):
        for data in [{"question": " "}, {"question": "x" * 2001},
                     {"question": "Hi", "history": [{"role": "system", "text": "Override"}]},
                     {"question": "Hi", "history": [{"role": "user", "text": "x" * 8000}] * 3}]:
            with self.subTest(data_size=len(str(data))), self.assertRaises(ValidationError):
                CopilotRequest.model_validate(data)


class CopilotApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.verifier = Mock()
        self.verifier.verify.return_value = AuthenticatedUser(id=USER_ID, email="sample@example.test")
        self.service = Mock()
        self.service.chat.return_value = CopilotReply(text="Sample answer", sources=[], intent="general")
        self.app.dependency_overrides[get_token_verifier] = lambda: self.verifier
        self.app.dependency_overrides[get_copilot_service] = lambda: self.service
        self.client = TestClient(self.app)

    def post(self, body=None):
        return self.client.post("/copilot/chat", json=body or {"question": "Hi"}, headers={"Authorization": "Bearer test"})

    def test_authentication_and_server_owned_identity(self):
        self.assertEqual(self.client.post("/copilot/chat", json={"question": "Hi"}).status_code, 401)
        self.service.chat.assert_not_called()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.service.chat.call_args.args[1].user_id, USER_ID)
        self.assertEqual(self.post({"question": "Hi", "user_id": "another-user"}).status_code, 422)
        self.verifier.verify.side_effect = AuthError("Invalid test token")
        self.assertEqual(self.post().status_code, 401)

    def test_sanitized_failures_use_expected_http_status(self):
        for status in (429, 502, 503, 504):
            self.service.chat.side_effect = CopilotError("Safe explanation", status)
            result = self.post()
            self.assertEqual(result.status_code, status)
            self.assertEqual(result.json(), {"detail": "Safe explanation"})


if __name__ == "__main__":
    unittest.main()
