import copy
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.config import SkillGapSettings
from app.services.skill_gap_agent import SkillGapAgentError, call_foundry, response_format
from scripts.test_skill_gap_structured_local import JobsOutput, ResumeOutput, FinalOutput


class ApiSchemaTests(unittest.TestCase):
    def setUp(self):
        self.settings = SkillGapSettings(_env_file=None,
            skill_gap_foundry_project_endpoint="https://example.invalid/api/projects/test",
            skill_gap_foundry_agent_name="test-agent")
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.conversations.create.return_value.id = "test-conversation"
        self.response = SimpleNamespace(id="response-test", status="completed", model="test-model",
            output_text='{"postings":[]}', output=[], usage={"input_tokens": 10, "output_tokens": 5},
            incomplete_details=None, text={"format": {"type": "json_schema", "strict": True}})
        self.client.responses.create.return_value = self.response
        self.project = MagicMock()
        self.project.__enter__.return_value = self.project
        self.project.get_openai_client.return_value = self.client

    def invoke(self, **kwargs):
        with patch("azure.ai.projects.AIProjectClient", return_value=self.project), \
             patch("azure.identity.DefaultAzureCredential"):
            return call_foundry({"task": "test"}, "test instructions", self.settings, **kwargs)

    def test_three_schemas_are_strict_and_not_mutated(self):
        for model in (JobsOutput, ResumeOutput, FinalOutput):
            with self.subTest(model=model.__name__):
                schema = model.model_json_schema()
                original = copy.deepcopy(schema)
                result = response_format(schema, model.__name__)
                self.assertTrue(result["strict"])
                self.assertEqual("json_schema", result["type"])
                self.assertEqual(schema, result["schema"])
                result["schema"]["title"] = "changed"
                self.assertEqual(original, schema)

    def test_schema_is_an_api_parameter_not_only_prompt_text(self):
        metadata = {}
        schema = JobsOutput.model_json_schema()
        result = self.invoke(output_schema=schema, schema_name="extract_job_requirements",
                             max_output_tokens=8000, response_metadata=metadata)
        self.assertEqual('{"postings":[]}', result)
        kwargs = self.client.responses.create.call_args.kwargs
        self.assertEqual({"format": {"type": "json_schema", "name": "extract_job_requirements",
                                      "strict": True, "schema": schema}}, kwargs["text"])
        self.assertEqual(8000, kwargs["max_output_tokens"])
        self.assertEqual("completed", metadata["status"])
        self.assertTrue(metadata["api_schema_requested"])
        self.assertEqual(5, metadata["usage"]["output_tokens"])
        self.client.conversations.delete.assert_called_once_with(conversation_id="test-conversation")

    def test_each_phase_uses_its_own_schema(self):
        for task, model in (("extract_job_requirements", JobsOutput),
                            ("extract_resume_evidence", ResumeOutput), ("explain_skill_gaps", FinalOutput)):
            self.invoke(output_schema=model.model_json_schema(), schema_name=task)
            self.assertEqual(task, self.client.responses.create.call_args.kwargs["text"]["format"]["name"])

    def test_legacy_call_does_not_silently_change_format(self):
        self.invoke()
        self.assertNotIn("text", self.client.responses.create.call_args.kwargs)

    def test_reasoning_override_is_explicit_only(self):
        self.invoke(reasoning_effort="low")
        self.assertEqual({"effort": "low"}, self.client.responses.create.call_args.kwargs["reasoning"])
        self.invoke()
        self.assertNotIn("reasoning", self.client.responses.create.call_args.kwargs)

    def test_longer_local_timeout_does_not_change_default_or_reasoning(self):
        self.invoke(request_timeout=300)
        self.assertEqual(300, self.project.get_openai_client.call_args.kwargs["timeout"])
        self.assertNotIn("reasoning", self.client.responses.create.call_args.kwargs)
        self.invoke()
        self.assertEqual(120, self.project.get_openai_client.call_args.kwargs["timeout"])

    def test_rejects_incomplete_response_and_records_partial_output(self):
        self.response.status = "incomplete"
        self.response.incomplete_details = {"reason": "max_output_tokens"}
        self.response.output_text = '{"postings":['
        metadata = {}
        with self.assertRaisesRegex(SkillGapAgentError, "status=incomplete"):
            self.invoke(output_schema=JobsOutput.model_json_schema(), response_metadata=metadata)
        self.assertEqual("max_output_tokens", metadata["incomplete_details"]["reason"])
        self.assertEqual('{"postings":[', metadata["partial_output_text"])
        self.client.conversations.delete.assert_called_once()

    def test_refusal_is_not_accepted_as_json(self):
        self.response.output = [SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
        with self.assertRaisesRegex(SkillGapAgentError, "refused=True"):
            self.invoke(output_schema=JobsOutput.model_json_schema())

    def test_schema_rejection_never_falls_back_to_prompt_only(self):
        error = RuntimeError("provider rejected schema")
        error.status_code = 400
        error.body = {"error": {"code": "invalid_payload", "param": "text",
                                "message": "Not allowed when agent is specified."}}
        self.client.responses.create.side_effect = error
        metadata = {}
        with self.assertRaisesRegex(SkillGapAgentError, "status=400"):
            self.invoke(output_schema=JobsOutput.model_json_schema(), response_metadata=metadata)
        self.client.responses.create.assert_called_once()
        self.assertEqual("text", metadata["request_error"]["param"])
        self.assertEqual("invalid_payload", metadata["request_error"]["code"])

    def test_unknowns_keep_nullable_types(self):
        schema = FinalOutput.model_json_schema()
        result = response_format(schema, "explain_skill_gaps")
        options = result["schema"]["$defs"]["ResumeMatch"]["properties"]["evidence_score"]["anyOf"]
        self.assertIn({"type": "null"}, options)

    def test_schema_contract_errors_are_detected_locally(self):
        for schema in ({"type": "array"},
                       {"type": "object", "properties": {}, "required": []},
                       {"type": "object", "properties": {"x": {"type": "string"}},
                        "required": [], "additionalProperties": False}):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                response_format(schema, "test")


if __name__ == "__main__":
    unittest.main()
