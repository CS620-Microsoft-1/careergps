"""Offline acceptance checks for the single-Agent read-only conversation loop."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:fake@127.0.0.1:1/test")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openai.types.responses import ResponseFunctionToolCall

from app.api.deps import get_account_service, get_token_verifier
from app.api.routes.copilot import get_copilot_service, get_readonly_resume_source, get_readonly_report_source, router
from app.core.config import CopilotSettings
from app.core.security import AuthenticatedUser
from app.schemas.copilot import CopilotRequest
from app.services.copilot.agent import (
    ChatContext, CopilotError, FoundryCopilotService, agent_definition,
    run_readonly_conversation,
)
from app.services.copilot.read_tools import ReadOnlyTools, ToolContractError

USER = UUID("11111111-1111-4111-8111-111111111111")
RESUME = UUID("33333333-3333-4333-8333-333333333333")
RUN = "a" * 32
FAMILY = "ai_engineer"
REFERENCE = {"type": "agent_reference", "name": "orchestrator-chatbot", "version": "fixture-readonly"}
RESUME_SOURCE = f"resume:{RESUME}:technical_skills"
REPORT_SOURCE = f"report:{RUN}:summary"


def request(**changes):
    return CopilotRequest(**{"question": "What are my saved skills?", "jobFamily": FAMILY, **changes})


def function(name="get_confirmed_resume", arguments=None, call_id="read-1"):
    if arguments is None:
        arguments = {"sections": ["technical_skills"]} if name == "get_confirmed_resume" else {}
    return {"type": "function_call", "name": name, "call_id": call_id,
            "arguments": json.dumps(arguments) if not isinstance(arguments, str) else arguments}


def response(*outputs, answer=None, status="completed", text=None):
    output_text = json.dumps(answer) if answer is not None else (text or "")
    values = list(outputs)
    if answer is not None or text is not None:
        values.append({"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": output_text}]})
    return SimpleNamespace(status=status, output_text=output_text,
        output=[Mock(model_dump=Mock(return_value=deepcopy(value))) for value in values])


class ReadOnlyConversationTests(unittest.TestCase):
    def setUp(self):
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Offline test attempted network access"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.resumes = Mock()
        self.reports = Mock()
        self.snapshot = SimpleNamespace(id=RESUME, user_id=USER, job_family=FAMILY,
            filename="saved.pdf", confirmed_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
            confirmed_data={"technical_skills": [" Python ", "SQL", "SQL"],
                "education": [], "work_experience": [{"title": "Student", "content": ["Built a course website."]}],
                "research_experience": [], "projects": [],
                "personal_information": {"emails": ["private@example.invalid"]}},
            resume_hash="b" * 64)
        self.resumes.get_snapshot.return_value = self.snapshot
        self.saved_report = {"run_id": RUN, "resume_id": str(RESUME), "job_family": FAMILY,
            "created_at": "2026-11-17T10:00:00+00:00", "completed_at": "2026-11-17T10:00:10+00:00",
            "calculation_fingerprint": "c" * 64,
            "freshness": "Saved result; current algorithm was not revalidated.",
            "report": {"priority_order": ["sql"], "unscored_skill_ids": ["deployment"],
                "skills": [{"skill_id": "sql", "skill_name": "SQL", "calculation_state": "scored",
                    "resume_evidence_strength": 0.5, "skill_gap": 0.5, "priority": 0.25,
                    "agent_assessment": {"evidence": ["Built a course website."]}},
                    {"skill_id": "deployment", "skill_name": "Deployment", "calculation_state": "pending",
                     "resume_evidence_strength": None, "skill_gap": None, "priority": None}],
                "source_index": {"e1": {"text": "Built a course website."}},
                "limitations": ["Resume evidence is not a proficiency test."]}}
        self.reports.get_report.return_value = deepcopy(self.saved_report)
        self.tools = self.make_tools()
        self.client = SimpleNamespace(responses=Mock())
        self.now = 0

    def make_tools(self):
        return ReadOnlyTools(USER, FAMILY, self.resumes, self.reports, report_id=RUN)

    def run_chat(self, *responses, chat_request=None, deadline=60):
        self.client.responses.create.side_effect = responses
        with patch("app.services.copilot.agent.monotonic", side_effect=lambda: self.now):
            return run_readonly_conversation(self.client, REFERENCE, chat_request or request(),
                                            self.tools, deadline=deadline)

    def test_greeting_rewrite_and_follow_up_complete_in_one_request_without_saved_data(self):
        for question in ("Hi", "Rewrite this fictional sentence: I built a website.", "Make the last sentence shorter."):
            with self.subTest(question=question):
                self.client.responses.reset_mock()
                current = request(question=question, history=[{"role": "user", "text": "I built a website."},
                    {"role": "assistant", "text": "I created a website."}])
                reply = self.run_chat(response(answer={"text": "The complete reply.", "source_ids": []}), chat_request=current)
                self.assertEqual(reply.text, "The complete reply.")
                self.assertEqual(reply.sources, [])
                self.client.responses.create.assert_called_once()
                sent = json.loads(self.client.responses.create.call_args.kwargs["input"][0]["content"])
                self.assertEqual(sent["history"], current.model_dump()["history"])
                self.assertEqual(sent["question"], current.question)
                self.assertNotIn(str(USER), json.dumps(sent))
        self.resumes.get_snapshot.assert_not_called()
        self.reports.get_report.assert_not_called()

    def test_resume_read_replays_reasoning_and_tool_result_then_returns_backend_citation(self):
        reasoning = {"type": "reasoning", "id": "reasoning-1", "summary": [], "encrypted_content": "opaque-content"}
        first = response(reasoning, function())
        # Exercise the real SDK's alias rather than only dictionary-based stand-ins.
        first.output[1] = ResponseFunctionToolCall(**{**function(), "async": False})
        reply = self.run_chat(first,
            response(answer={"text": "Your saved skills include Python and SQL.", "source_ids": [RESUME_SOURCE]}))
        self.assertEqual(reply.sources[0].id, RESUME_SOURCE)
        self.assertIn("SQL", reply.sources[0].excerpt)
        self.resumes.get_snapshot.assert_called_once_with(USER, FAMILY)
        calls = self.client.responses.create.call_args_list
        self.assertEqual(len(calls), 2)
        replay = calls[1].kwargs["input"]
        self.assertIn(reasoning, replay)
        replayed_call = next(item for item in replay if item.get("type") == "function_call")
        self.assertIs(replayed_call["async"], False)
        self.assertNotIn("async_", replayed_call)
        outputs = [item for item in replay if item.get("type") == "function_call_output"]
        self.assertEqual(outputs[0]["call_id"], "read-1")
        tool_result = json.loads(outputs[0]["output"])
        self.assertEqual(tool_result["data"]["sections"], {"technical_skills": [" Python ", "SQL", "SQL"]})
        self.assertNotIn("private@example.invalid", outputs[0]["output"])
        for call in calls:
            self.assertEqual(call.kwargs["extra_body"]["agent_reference"], REFERENCE)
            self.assertFalse(call.kwargs["store"])
            self.assertFalse(call.kwargs["parallel_tool_calls"])
            self.assertEqual(call.kwargs["max_output_tokens"], 2500)
            self.assertIn("reasoning.encrypted_content", call.kwargs["include"])
            self.assertNotIn("previous_response_id", call.kwargs)
            self.assertNotIn("conversation", call.kwargs)

    def test_report_read_preserves_saved_scores_uncertainty_and_validated_page_selector(self):
        before = deepcopy(self.saved_report)
        reply = self.run_chat(response(function("get_skill_gap_report")),
            response(answer={"text": "The saved SQL gap is 0.5; deployment remains unscored.", "source_ids": [REPORT_SOURCE]}))
        self.reports.get_report.assert_called_once_with(self.snapshot, report_id=RUN)
        tool_output = next(item for item in self.client.responses.create.call_args.kwargs["input"]
                           if item.get("type") == "function_call_output")
        self.assertEqual(json.loads(tool_output["output"])["data"]["report"], before["report"])
        self.assertIn("SQL | 0.5 | 0.5 | 0.25 | scored", reply.sources[0].excerpt)
        self.assertIn("Deployment | not scored | not scored | not scored | pending", reply.sources[0].excerpt)
        self.assertEqual(self.saved_report, before)

    def test_large_report_and_all_resume_sections_offer_at_most_six_valid_sources(self):
        large = deepcopy(self.saved_report)
        large["report"]["skills"] = [
            {"skill_id": f"skill-{index}", "skill_name": f"Skill {index}",
             "calculation_state": "scored", "resume_evidence_strength": 0.5,
             "skill_gap": 0.5, "priority": 0.25,
             "agent_assessment": {"evidence": [f"Original evidence {index}."]}}
            for index in range(23)]
        large["report"]["priority_order"] = [row["skill_id"] for row in large["report"]["skills"]]
        large["report"]["unscored_skill_ids"] = []
        self.reports.get_report.return_value = large
        before = deepcopy(large)
        sections = ["technical_skills", "education", "work_experience", "research_experience", "projects"]
        resume_ids = [f"resume:{RESUME}:{section}" for section in sections]
        ids = [*resume_ids, REPORT_SOURCE]
        reply = self.run_chat(response(function(arguments={"sections": sections})),
            response(function("get_skill_gap_report", call_id="read-2")),
            response(answer={"text": "A summary of the saved report and resume.", "source_ids": ids}))
        self.assertEqual([source.id for source in reply.sources], ids)
        self.assertEqual(len(self.tools.sources), 6)
        replay = self.client.responses.create.call_args.kwargs["input"]
        resume_result = json.loads([item["output"] for item in replay if item.get("type") == "function_call_output"][0])
        self.assertEqual(set(resume_result["data"]["sections"]), set(sections))
        self.assertNotIn("personal_information", resume_result["data"]["sections"])
        self.assertNotIn("user_id", resume_result["data"])
        report_result = json.loads([item["output"] for item in replay if item.get("type") == "function_call_output"][-1])
        self.assertEqual(report_result["data"], before)
        self.assertEqual(len(report_result["sources"]), 1)
        self.assertIn("Skill 22 | 0.5 | 0.5 | 0.25 | scored", reply.sources[-1].excerpt)
        self.assertEqual(large, before)

    def test_both_sources_use_one_main_agent_three_responses_and_one_resume_snapshot(self):
        reply = self.run_chat(response(function()), response(function("get_skill_gap_report", call_id="read-2")),
            response(answer={"text": "Here is a summary of the saved resume and report.",
                             "source_ids": [RESUME_SOURCE, REPORT_SOURCE]}))
        self.assertEqual(len(reply.sources), 2)
        self.assertEqual(self.client.responses.create.call_count, 3)
        self.resumes.get_snapshot.assert_called_once_with(USER, FAMILY)
        self.reports.get_report.assert_called_once()
        self.assertEqual([call.kwargs["tool_choice"] for call in self.client.responses.create.call_args_list],
                         ["auto", "auto", "none"])
        self.assertEqual({call.kwargs["extra_body"]["agent_reference"]["name"]
                          for call in self.client.responses.create.call_args_list}, {"orchestrator-chatbot"})

    def test_history_does_not_authorize_an_unread_source(self):
        old_history = [{"role": "assistant", "text": f"Previously claimed source {RESUME_SOURCE}"}]
        with self.assertRaises(CopilotError):
            self.run_chat(response(answer={"text": "I read it.", "source_ids": [RESUME_SOURCE]}),
                          chat_request=request(history=old_history))
        self.resumes.get_snapshot.assert_not_called()
        self.client.responses.create.assert_called_once()

    def test_unknown_and_duplicate_source_ids_are_rejected_after_a_valid_read(self):
        for ids in ([], ["report:unread:summary"], [RESUME_SOURCE, RESUME_SOURCE]):
            with self.subTest(ids=ids):
                self.tools = self.make_tools()
                self.client.responses.reset_mock()
                with self.assertRaises(CopilotError):
                    self.run_chat(response(function()), response(answer={"text": "A reply", "source_ids": ids}))
                self.assertEqual(self.client.responses.create.call_count, 2)

    def test_failure_diagnostics_record_field_and_type_without_reply_or_identity(self):
        with self.assertLogs("app.services.copilot.agent", level="WARNING") as captured:
            with self.assertRaises(CopilotError):
                self.run_chat(response(function()), response(answer={
                    "text": "PRIVATE_REPLY_BODY", "source_ids": [RESUME_SOURCE] * 9}))
        diagnostic = " ".join(captured.output)
        self.assertIn("source_ids", diagnostic)
        self.assertIn("too_long", diagnostic)
        for private in ("PRIVATE_REPLY_BODY", str(USER), str(RESUME), "Python"):
            self.assertNotIn(private, diagnostic)
        with self.assertLogs("app.services.copilot.agent", level="WARNING") as captured:
            with self.assertRaises(CopilotError):
                self.run_chat(response(answer={"text": "PRIVATE_REPLY_BODY", "source_ids": [],
                                              "PRIVATE_KEY_NAME": "PRIVATE_VALUE"}))
        diagnostic = " ".join(captured.output)
        self.assertIn("extra_forbidden", diagnostic)
        for private in ("PRIVATE_KEY_NAME", "PRIVATE_VALUE", "PRIVATE_REPLY_BODY"):
            self.assertNotIn(private, diagnostic)

    def test_invalid_tool_arguments_identity_sql_and_unregistered_actions_never_read(self):
        invalid = [("get_confirmed_resume", "not JSON"), ("get_confirmed_resume", "[]"),
            ("get_confirmed_resume", '{"sections":["technical_skills"],"sections":["projects"]}'),
            ("get_confirmed_resume", '{"sections":NaN}'), ("get_confirmed_resume", {}),
            ("get_confirmed_resume", {"sections": []}),
            ("get_confirmed_resume", {"sections": [None]}),
            ("get_confirmed_resume", {"sections": "projects"}),
            ("get_confirmed_resume", {"sections": ["technical_skills", "technical_skills"]}),
            ("get_confirmed_resume", {"sections": ["personal_information"]}),
            ("get_confirmed_resume", {"sections": ["technical_skills"], "user_id": str(USER)}),
            ("get_confirmed_resume", {"sections": ["technical_skills"], "sql": "UPDATE users SET id=1"}),
            ("get_skill_gap_report", {"report_id": RUN}), ("get_skill_gap_report", {"resume_id": str(RESUME)}),
            ("save_plan", {}), ("run_analysis", {})]
        for name, arguments in invalid:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ToolContractError):
                self.tools.execute(name, arguments if isinstance(arguments, str) else json.dumps(arguments))
        self.resumes.get_snapshot.assert_not_called()
        self.reports.get_report.assert_not_called()
        self.assertEqual(self.tools.executions, 0)

    def test_identical_read_is_cached_and_caller_mutation_does_not_change_the_cached_data(self):
        raw = json.dumps({"sections": ["technical_skills"]})
        first = self.tools.execute("get_confirmed_resume", raw)
        first["data"]["sections"]["technical_skills"].append("Invented")
        second = self.tools.execute("get_confirmed_resume", raw)
        self.assertEqual(second["data"]["sections"]["technical_skills"], [" Python ", "SQL", "SQL"])
        self.resumes.get_snapshot.assert_called_once()
        self.assertEqual(self.tools.executions, 1)

    def test_missing_or_failed_read_returns_no_sources_and_does_not_retry(self):
        for status in (404, 409, 503):
            with self.subTest(status=status):
                self.tools = self.make_tools()
                self.reports.get_report.reset_mock()
                self.reports.get_report.side_effect = HTTPException(status, "The saved report is unavailable.")
                reply = self.run_chat(response(function("get_skill_gap_report")),
                    response(answer={"text": "The saved report is unavailable.", "source_ids": []}))
                self.assertEqual(reply.sources, [])
                self.reports.get_report.assert_called_once()
                result = next(item for item in self.client.responses.create.call_args.kwargs["input"]
                              if item.get("type") == "function_call_output")
                self.assertEqual(json.loads(result["output"])["status_code"], status)

    def test_oversized_data_fails_without_issuing_sources_or_mutating_saved_data(self):
        self.snapshot.confirmed_data["technical_skills"] = ["x" * 80_001]
        result = self.tools.execute("get_confirmed_resume", '{"sections":["technical_skills"]}')
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["status_code"], 503)
        self.assertEqual(self.tools.sources, {})
        self.assertEqual(len(self.snapshot.confirmed_data["technical_skills"][0]), 80_001)

    def test_duplicate_call_ids_and_unsupported_tools_fail_without_additional_reads(self):
        cases = [response(function(call_id="same"), function(call_id="same")),
                 response({"type": "web_search_call", "id": "blocked"}),
                 response(function("delete_resume"))]
        for first in cases:
            with self.subTest(output=first.output):
                self.tools = self.make_tools()
                self.client.responses.reset_mock()
                with self.assertRaises(CopilotError):
                    self.run_chat(first)
                self.client.responses.create.assert_called_once()
        self.resumes.get_snapshot.assert_not_called()
        with self.assertRaises(CopilotError):
            self.run_chat(response(function(call_id="same")), response(function("get_skill_gap_report", call_id="same")))
        self.reports.get_report.assert_not_called()

    def test_entire_tool_batch_is_validated_before_any_read(self):
        with self.assertRaises(CopilotError):
            self.run_chat(response(function(), function("save_plan", call_id="blocked")))
        self.resumes.get_snapshot.assert_not_called()
        self.reports.get_report.assert_not_called()
        self.client.responses.create.assert_called_once()

    def test_authenticated_http_chat_reaches_real_service_tools_and_returns_cited_data(self):
        app = FastAPI()
        app.include_router(router)
        verifier = Mock()
        verifier.verify.return_value = AuthenticatedUser(USER, "synthetic@example.invalid")
        settings = CopilotSettings(_env_file=None,
            orchestrator_foundry_project_endpoint="https://fixture.invalid/api/projects/test",
            orchestrator_foundry_agent_name=REFERENCE["name"],
            orchestrator_foundry_agent_version=REFERENCE["version"], copilot_readonly_enabled=True)
        app.dependency_overrides[get_token_verifier] = lambda: verifier
        app.dependency_overrides[get_readonly_resume_source] = lambda: self.resumes
        app.dependency_overrides[get_readonly_report_source] = lambda: self.reports
        app.dependency_overrides[get_copilot_service] = lambda: FoundryCopilotService(settings)
        app.dependency_overrides[get_account_service] = lambda: (_ for _ in ()).throw(
            AssertionError("The chat must not acquire a write-capable account service"))
        client = MagicMock()
        client.__enter__.return_value = client
        client.responses.create.side_effect = [response(function("get_skill_gap_report")),
            response(answer={"text": "The saved report records a SQL gap of 0.5.", "source_ids": [REPORT_SOURCE]})]
        project = MagicMock()
        project.__enter__.return_value = project
        project.get_openai_client.return_value = client
        project.agents.get_version.return_value = SimpleNamespace(
            definition=SimpleNamespace(as_dict=lambda: agent_definition("fixture-model")))
        credential = MagicMock()
        credential.__enter__.return_value = credential
        modules = {"azure.ai.projects": SimpleNamespace(AIProjectClient=Mock(return_value=project)),
                   "azure.identity": SimpleNamespace(DefaultAzureCredential=Mock(return_value=credential))}
        with patch.dict("sys.modules", modules), TestClient(app) as http:
            result = http.post("/copilot/chat", json={"question": "Why does my saved report show a SQL gap?",
                "history": [], "jobFamily": FAMILY, "reportId": RUN},
                headers={"Authorization": "Bearer synthetic-token"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["mode"], "foundry_chat")
        self.assertEqual(result.json()["sources"][0]["id"], REPORT_SOURCE)
        self.assertIn("SQL | 0.5 | 0.5 | 0.25 | scored", result.json()["sources"][0]["excerpt"])
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.resumes.require_account.assert_called_once_with(USER)
        self.resumes.get_snapshot.assert_called_once_with(USER, FAMILY)
        self.reports.get_report.assert_called_once_with(self.snapshot, report_id=RUN)
        self.assertEqual(client.responses.create.call_count, 2)

    def test_final_response_budget_rejects_more_tools_and_never_starts_a_fourth_request(self):
        with self.assertRaises(CopilotError):
            self.run_chat(response(function()), response(function("get_skill_gap_report", call_id="read-2")),
                          response(function(call_id="read-3")))
        self.assertEqual(self.client.responses.create.call_count, 3)
        self.assertEqual(self.tools.executions, 2)
        self.assertEqual(self.client.responses.create.call_args.kwargs["tool_choice"], "none")

    def test_invalid_incomplete_and_unstructured_final_answers_never_return_success(self):
        bad = [response(answer={"text": "", "source_ids": []}), response(answer={"text": "No sources field"}),
               response(answer={"text": "Hello", "source_ids": [], "reasoning": "private"}),
               response(text="plain text"), response(answer={"text": "Hello", "source_ids": []}, status="incomplete")]
        for item in bad:
            with self.subTest(text=item.output_text):
                self.client.responses.reset_mock()
                with self.assertRaises(CopilotError):
                    self.run_chat(item)
                self.client.responses.create.assert_called_once()

    def test_deadline_covers_model_and_read_work_without_retry(self):
        self.now = 61
        with self.assertRaises(CopilotError) as caught:
            self.run_chat()
        self.assertEqual(caught.exception.status_code, 504)
        self.client.responses.create.assert_not_called()
        self.now = 45
        self.run_chat(response(answer={"text": "Hello", "source_ids": []}))
        self.assertEqual(self.client.responses.create.call_args.kwargs["timeout"], 15)
        self.now = 0
        def slow_snapshot(*_):
            self.now = 61
            return self.snapshot
        self.resumes.get_snapshot.side_effect = slow_snapshot
        self.client.responses.reset_mock()
        with self.assertRaises(CopilotError) as caught:
            self.run_chat(response(function()))
        self.assertEqual(caught.exception.status_code, 504)
        self.client.responses.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
