"""Validate and invoke the same saved Agent version, with exactly one mock call."""
import json
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.services.skill_gaps import transport


class SkillGapTransportVersionTests(unittest.TestCase):
    def test_mismatched_or_missing_saved_contract_fails_before_inference(self):
        instructions, format_ = transport.load_local_contract()
        valid = {"instructions": instructions, "text": {"format": {"type": "json_schema", **format_}}}
        cases = (({}, None, "agent_version_unavailable"),
                 ({"instructions": instructions}, "28", "schema_mismatch"),
                 ({**valid, "instructions": "Different saved Instructions"}, "28", "instructions_mismatch"))
        for definition, version, code in cases:
            with self.subTest(code=code):
                saved = {}
                with self.assertRaises(transport.SkillGapConfigurationError) as error:
                    transport.validate_definition(definition, version, saved.__setitem__)
                self.assertEqual(error.exception.code, code)
                self.assertEqual(saved["configuration_check.json"]["model_calls"], 0)

    def test_drafts_are_excluded_and_checked_version_is_explicitly_called_once(self):
        modules = {name: ModuleType(name) for name in ("azure", "azure.ai", "azure.ai.projects", "azure.identity")}
        for name in ("azure", "azure.ai"):
            modules[name].__path__ = []
        modules["azure"].ai = modules["azure.ai"]
        modules["azure"].identity = modules["azure.identity"]
        modules["azure.ai"].projects = modules["azure.ai.projects"]
        credential, project, client = MagicMock(), MagicMock(), MagicMock()
        for context in (credential, project, client):
            context.__enter__.return_value = context
        modules["azure.identity"].DefaultAzureCredential = MagicMock(return_value=credential)
        modules["azure.ai.projects"].AIProjectClient = MagicMock(return_value=project)
        project.get_openai_client.return_value = client
        client.conversations.create.return_value = SimpleNamespace(id="test-conversation")
        instructions, format_ = transport.load_local_contract()
        definition = {"instructions": instructions, "text": {"format": {"type": "json_schema", **format_}}}
        project.agents.list_versions.return_value = [SimpleNamespace(version="28", definition=SimpleNamespace(as_dict=lambda: definition))]
        output = {"task": "extract_resume_evidence", "result": {}}
        raw = {"text": {"format": {"name": transport.SCHEMA_NAME, "type": "json_schema", "strict": True}}}
        client.responses.create.return_value = SimpleNamespace(status="completed", output_text=json.dumps(output),
            model_dump=lambda **kwargs: raw)
        saved, requested = {}, []
        settings = SimpleNamespace(skill_gap_foundry_project_endpoint="https://example.invalid/api/projects/test",
                                   skill_gap_foundry_agent_name="test-agent")
        with patch.dict(sys.modules, modules), patch("app.core.config.SkillGapSettings", return_value=settings):
            result = transport.invoke({"task": "extract_resume_evidence"}, saved.__setitem__, lambda: requested.append(1))
        self.assertEqual(result, output)
        project.agents.list_versions.assert_called_once_with("test-agent", limit=1, order="desc", include_drafts=False)
        project.get_openai_client.assert_called_once_with(timeout=480, max_retries=0)
        client.responses.create.assert_called_once()
        reference = client.responses.create.call_args.kwargs["extra_body"]["agent_reference"]
        self.assertEqual(reference, {"type": "agent_reference", "name": "test-agent", "version": "28"})
        self.assertEqual(requested, [1])
        client.conversations.delete.assert_called_once_with(conversation_id="test-conversation")
        self.assertTrue(saved["configuration_check.json"]["instructions_match"])


if __name__ == "__main__":
    unittest.main()
