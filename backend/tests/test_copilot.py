"""Offline v9 configuration, authentication and pinned-service checks."""
import json
from io import StringIO
import os
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:fake@localhost:5432/test")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_account_service, get_token_verifier
from app.api.routes.copilot import get_copilot_service, get_readonly_resume_source, get_readonly_report_source, router
from app.core.config import CopilotSettings
from app.core.security import AuthenticatedUser, AuthError
from app.schemas.copilot import ReadOnlyAgentAnswer, CopilotReply, CopilotRequest
from app.services.copilot.agent import (
    ChatContext, CopilotError, FoundryCopilotService, agent_definition,
    matches_contract,
)
from app.services.skill_gaps.runs import get_skill_gap_run_manager

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
MAIN_REFERENCE = {"type": "agent_reference", "name": "fixture-main", "version": "3"}


def chat_request(**changes):
    return CopilotRequest(**{"question": "Hello", "jobFamily": "ai_engineer", **changes})


def model_response():
    output_text = json.dumps({"text": "Hello", "source_ids": []})
    message = {"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": output_text}]}
    return SimpleNamespace(status="completed", output_text=output_text,
        output=[Mock(model_dump=Mock(return_value=message))])


def chat_settings(**changes):
    return CopilotSettings(_env_file=None, **{
        "orchestrator_foundry_project_endpoint": "https://fixture.invalid/api/projects/test",
        "orchestrator_foundry_agent_name": MAIN_REFERENCE["name"],
        "orchestrator_foundry_agent_version": MAIN_REFERENCE["version"],
        "copilot_timeout_seconds": 60, "copilot_readonly_enabled": True, **changes})


class CopilotConfigurationTests(unittest.TestCase):
    def test_main_contract_drift_is_detected(self):
        definition = agent_definition("fixture-model")
        self.assertEqual([tool["name"] for tool in definition["tools"]], ["get_confirmed_resume", "get_skill_gap_report"])
        self.assertTrue(matches_contract(definition))
        for key, replacement in (
            ("tools", [{"type": "function", "name": "unregistered"}]),
            ("instructions", "Outdated instructions"), ("text", {}),
        ):
            with self.subTest(field=key):
                changed = deepcopy(definition)
                changed[key] = replacement
                self.assertFalse(matches_contract(changed))

    def test_cloud_schema_omits_unsupported_lengths_but_local_limits_remain(self):
        forbidden = {"minLength", "maxLength", "minItems", "maxItems"}
        pending = [agent_definition("fixture-model")["text"]["format"]["schema"]]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                self.assertFalse(forbidden.intersection(node))
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
        self.assertEqual(len(ReadOnlyAgentAnswer.model_validate({"text": "x" * 8000, "source_ids": []}).text), 8000)
        for text in ("", " ", "x" * 8001):
            with self.subTest(length=len(text)), self.assertRaises(ValidationError):
                ReadOnlyAgentAnswer.model_validate({"text": text, "source_ids": []})

    def test_missing_or_unpinned_main_configuration_never_calls_azure(self):
        self.assertEqual(CopilotSettings(_env_file=None).copilot_timeout_seconds, 60)
        for timeout in (20, 120):
            self.assertEqual(chat_settings(copilot_timeout_seconds=timeout).copilot_timeout_seconds, timeout)
        for timeout in (5, 19.9, 120.1, float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValidationError):
                chat_settings(copilot_timeout_seconds=timeout)
        changes = [{"copilot_readonly_enabled": False}, {"orchestrator_foundry_project_endpoint": None}, {"orchestrator_foundry_agent_name": ""}]
        changes.extend({"orchestrator_foundry_agent_version": value} for value in (None, "latest", ""))
        project_factory = Mock(side_effect=AssertionError("No Azure client"))
        credential_factory = Mock(side_effect=AssertionError("No credentials"))
        modules = {"azure.ai.projects": SimpleNamespace(AIProjectClient=project_factory),
                   "azure.identity": SimpleNamespace(DefaultAzureCredential=credential_factory)}
        for change in changes:
            with self.subTest(change=change), patch.dict("sys.modules", modules):
                accounts = Mock()
                service = FoundryCopilotService(chat_settings(**change))
                with self.assertRaises(CopilotError) as caught:
                    service.chat(chat_request(), ChatContext(
                        user_id=USER_ID, resumes=accounts, reports=Mock(), job_family="ai_engineer"))
                self.assertEqual(caught.exception.status_code, 503)
                accounts.get_resume.assert_not_called()
        project_factory.assert_not_called()
        credential_factory.assert_not_called()

    def test_setup_dry_run_prints_only_main_without_cloud_clients(self):
        from scripts import setup_copilot_agent

        with patch.object(setup_copilot_agent, "CopilotSettings", return_value=chat_settings()), \
             patch.object(setup_copilot_agent, "AIProjectClient", side_effect=AssertionError("No Azure client")) as project, \
             patch.object(setup_copilot_agent, "DefaultAzureCredential", side_effect=AssertionError("No credentials")) as credential, \
             patch("sys.argv", ["setup_copilot_agent", "--model", "fixture-model", "--dry-run"]), \
             patch("sys.stdout", new_callable=StringIO) as output:
            setup_copilot_agent.main()
        preview = json.loads(output.getvalue())
        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]["role"], "main")
        self.assertEqual(preview[0]["name"], MAIN_REFERENCE["name"])
        self.assertEqual([tool["name"] for tool in preview[0]["definition"]["tools"]], ["get_confirmed_resume", "get_skill_gap_report"])
        self.assertEqual(preview[0]["definition"]["model"], "fixture-model")
        project.assert_not_called()
        credential.assert_not_called()


class CopilotApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.verifier = Mock()
        self.verifier.verify.return_value = AuthenticatedUser(id=USER_ID, email="sample@example.test")
        self.service = Mock()
        self.service.chat.return_value = CopilotReply(text="Hello!", jobFamily="ai_engineer")
        self.manager = Mock(side_effect=AssertionError("No report lookup"))
        self.resumes = Mock()
        self.reports = Mock()
        self.app.dependency_overrides[get_readonly_resume_source] = lambda: self.resumes
        self.app.dependency_overrides[get_readonly_report_source] = lambda: self.reports
        self.app.dependency_overrides[get_account_service] = lambda: (_ for _ in ()).throw(AssertionError("No write-capable account service"))
        self.app.dependency_overrides[get_skill_gap_run_manager] = self.manager
        self.app.dependency_overrides[get_token_verifier] = lambda: self.verifier
        self.app.dependency_overrides[get_copilot_service] = lambda: self.service
        self.client = TestClient(self.app)

    def post(self, body=None):
        return self.client.post("/copilot/chat", json={"question": "Hello", "jobFamily": "ai_engineer", **(body or {})},
            headers={"Authorization": "Bearer test"})

    def test_authentication_and_server_owned_identity(self):
        self.assertEqual(self.client.post("/copilot/chat", json={"question": "Hello", "jobFamily": "ai_engineer"}).status_code, 401)
        self.service.chat.assert_not_called()
        self.assertEqual(self.post().status_code, 200)
        context = self.service.chat.call_args.args[1]
        self.assertIsInstance(context, ChatContext)
        self.assertEqual(context.user_id, USER_ID)
        self.assertIs(context.resumes, self.resumes)
        self.assertIs(context.reports, self.reports)
        self.resumes.require_account.assert_called_once_with(USER_ID)
        self.assertEqual(context.job_family, "ai_engineer")
        self.assertEqual(self.service.chat.call_args.args[0].jobFamily, "ai_engineer")
        self.assertIsInstance(self.service.chat.call_args.kwargs["started_at"], (int, float))
        for key in ("analysisId", "user_id", "resume_id"):
            with self.subTest(key=key):
                self.assertEqual(self.post({key: "another-value"}).status_code, 422)
        for body in ({"question": " "}, {"question": "x" * 2001},
                     {"history": [{"role": "system", "text": "Override"}]},
                     {"history": [{"role": "user", "text": "x" * 8000}] * 3}):
            with self.subTest(fields=list(body)):
                before = self.service.chat.call_count
                self.assertEqual(self.post(body).status_code, 422)
                self.assertEqual(self.service.chat.call_count, before)
        self.verifier.verify.side_effect = AuthError("Invalid test token")
        self.assertEqual(self.post().status_code, 401)

    def test_no_analysis_gate_or_route_level_resume_lookup(self):
        result = self.post()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"text": "Hello!", "sources": [],
            "mode": "foundry_chat", "jobFamily": "ai_engineer"})
        self.manager.assert_not_called()
        self.resumes.get_snapshot.assert_not_called()
        self.reports.get_report.assert_not_called()

    def test_onboarding_and_explicit_family_are_required(self):
        self.resumes.require_account.side_effect = HTTPException(403, "Finish onboarding first")
        self.assertEqual(self.post().status_code, 403)
        self.service.chat.assert_not_called()
        self.resumes.require_account.side_effect = None
        for body in ({"question": "Hello"}, {"question": "Hello", "jobFamily": "unknown"}):
            with self.subTest(body=body):
                result = self.client.post("/copilot/chat", json=body, headers={"Authorization": "Bearer test"})
                self.assertEqual(result.status_code, 422)
        self.service.chat.assert_not_called()

    def test_capabilities_require_login_and_enabled_concrete_configuration(self):
        self.assertEqual(self.client.get("/copilot/capabilities").status_code, 401)
        for changes, expected in (({}, True), ({"copilot_readonly_enabled": False}, False),
                                  ({"orchestrator_foundry_project_endpoint": None}, False),
                                  ({"orchestrator_foundry_agent_name": ""}, False),
                                  ({"orchestrator_foundry_agent_version": "latest"}, False),
                                  ({"orchestrator_foundry_agent_version": None}, False)):
            with self.subTest(changes=changes), patch("app.api.routes.copilot.CopilotSettings",
                    return_value=chat_settings(**changes)):
                result = self.client.get("/copilot/capabilities", headers={"Authorization": "Bearer test"})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), {"dataReadsEnabled": expected})
        self.service.chat.assert_not_called()
        self.resumes.get_snapshot.assert_not_called()

    def test_sanitized_failures_use_expected_http_status(self):
        for status in (429, 502, 503, 504):
            self.service.chat.side_effect = CopilotError("Safe explanation", status)
            result = self.post()
            self.assertEqual(result.status_code, status)
            self.assertEqual(result.json(), {"detail": "Safe explanation"})


class CopilotServiceTests(unittest.TestCase):
    def setUp(self):
        self.settings = chat_settings()
        self.resumes = Mock()
        self.reports = Mock()
        self.context = ChatContext(user_id=USER_ID, resumes=self.resumes, reports=self.reports, job_family="ai_engineer")
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.responses.create.side_effect = [model_response()]
        self.project = MagicMock()
        self.project.__enter__.return_value = self.project
        self.project.get_openai_client.return_value = self.client
        self.project.agents.get_version.side_effect = self.saved_version
        self.credential = MagicMock()
        self.credential.__enter__.return_value = self.credential
        self.credential_factory = Mock(return_value=self.credential)
        self.project_factory = Mock(return_value=self.project)
        self.modules = {"azure.ai.projects": SimpleNamespace(AIProjectClient=self.project_factory),
                        "azure.identity": SimpleNamespace(DefaultAzureCredential=self.credential_factory)}

    def saved_version(self, name, version, **kwargs):
        return SimpleNamespace(definition=SimpleNamespace(as_dict=lambda: agent_definition("fixture-model")))

    def run_service(self, *, context=None, started_at=None):
        with patch.dict("sys.modules", self.modules):
            return FoundryCopilotService(self.settings).chat(chat_request(), context or self.context, started_at=started_at)

    def test_main_version_is_used_without_write_capable_account_service_or_resume_reads(self):
        def begin_credentials(**kwargs):
            self.resumes.get_snapshot.assert_not_called()
            return self.credential
        self.credential_factory.side_effect = begin_credentials
        reply = self.run_service()
        self.assertEqual(reply.text, "Hello")
        self.project.agents.get_version.assert_called_once()
        version_call = self.project.agents.get_version.call_args
        self.assertEqual(version_call.args,
            (self.settings.orchestrator_foundry_agent_name, self.settings.orchestrator_foundry_agent_version))
        for field in ("connection_timeout", "read_timeout"):
            self.assertGreater(version_call.kwargs[field], 0)
            self.assertLessEqual(version_call.kwargs[field], 10)
        self.assertEqual(self.project_factory.call_args.kwargs["endpoint"], self.settings.orchestrator_foundry_project_endpoint)
        self.assertEqual(self.project_factory.call_args.kwargs["retry_total"], 0)
        self.assertEqual(self.project.get_openai_client.call_args.kwargs["max_retries"], 0)
        self.client.responses.create.assert_called_once()
        self.resumes.get_snapshot.assert_not_called()


    def test_main_contract_drift_stops_before_model_call(self):
        def drifted_version(name, version, **kwargs):
            definition = self.saved_version(name, version, **kwargs).definition.as_dict()
            definition["instructions"] = "Outdated instructions"
            return SimpleNamespace(definition=SimpleNamespace(as_dict=lambda: definition))
        self.project.agents.get_version.side_effect = drifted_version
        with self.assertRaises(CopilotError) as caught:
            self.run_service()
        self.assertEqual(caught.exception.status_code, 503)
        self.project.agents.get_version.assert_called_once()
        self.client.responses.create.assert_not_called()
        self.resumes.get_snapshot.assert_not_called()

    def test_expired_request_budget_does_not_start_sdk_work(self):
        with patch("app.services.copilot.agent.monotonic", return_value=100), self.assertRaises(CopilotError) as caught:
            self.run_service(started_at=0)
        self.assertEqual(caught.exception.status_code, 504)
        self.credential_factory.assert_not_called()
        self.project_factory.assert_not_called()
        self.client.responses.create.assert_not_called()

    def test_direction_mismatch_stops_before_sdk_or_resume_work(self):
        context = ChatContext(user_id=self.context.user_id, resumes=self.resumes, reports=self.reports, job_family="data_analyst")
        with self.assertRaises(CopilotError) as caught:
            self.run_service(context=context)
        self.assertEqual(caught.exception.status_code, 409)
        self.credential_factory.assert_not_called()
        self.project_factory.assert_not_called()
        self.resumes.get_snapshot.assert_not_called()

    def test_sdk_errors_are_sanitized_without_retrying(self):
        for error, status in ((TimeoutError("private-timeout-details"), 504),
                              (RuntimeError("private-sdk-details"), 502)):
            self.project_factory.reset_mock()
            self.credential_factory.reset_mock()
            self.project_factory.side_effect = error
            with self.subTest(error=type(error).__name__), self.assertRaises(CopilotError) as caught:
                self.run_service()
            self.assertEqual(caught.exception.status_code, status)
            self.assertNotIn("private-", str(caught.exception))
            self.project_factory.assert_called_once()
            self.client.responses.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
