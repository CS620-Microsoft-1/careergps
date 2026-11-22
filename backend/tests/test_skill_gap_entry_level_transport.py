"""Offline integration checks for repository-backed production Agent bindings."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call, patch

from app.core.config import SkillGapSettings
from app.services.skill_gaps import entry_level_transport as transport
from app.services.skill_gaps.entry_level import build_format
from app.services.skill_gaps.entry_level_agents import AgentBundleError, FAMILY_SLUGS, digest, load_bundle
from app.services.skill_gaps.skill_groups import GROUPS
from app.services.skill_gaps.transport import SkillGapConfigurationError


@contextmanager
def fake_saved_agents(*, mutate=None, failure=None):
    bundle = load_bundle()
    by_name = {item.name: item for item in bundle.values()}
    project, credential = MagicMock(), MagicMock()
    project.__enter__.return_value = project
    credential.__enter__.return_value = credential

    def get_version(name, version):
        if failure is not None:
            raise failure
        expected = by_name[name]
        saved = SimpleNamespace(name=expected.name, version=expected.version, draft=False,
                                definition=deepcopy(expected.definition))
        if mutate:
            mutate(saved)
        return saved

    project.agents.get_version.side_effect = get_version
    with patch("azure.ai.projects.AIProjectClient", return_value=project) as project_factory, \
            patch("azure.identity.DefaultAzureCredential", return_value=credential) as credential_factory, \
            patch.object(transport, "create_response", side_effect=AssertionError("Unexpected inference")) as response:
        yield SimpleNamespace(project=project, project_factory=project_factory,
                              credential_factory=credential_factory, response=response)


class EntryLevelTransportTests(unittest.TestCase):
    def setUp(self):
        self.settings = SkillGapSettings(_env_file=None,
            skill_gap_foundry_project_endpoint="https://fixture.invalid/api/projects/review")
        self.saved = {}

    def save(self, group, filename, value):
        self.saved[group, filename] = deepcopy(value)

    def assert_no_inference(self, sdk):
        sdk.project.get_openai_client.assert_not_called()
        sdk.response.assert_not_called()

    def test_configuration_signatures_use_all_nine_production_pins_offline(self):
        bundle = load_bundle()
        with fake_saved_agents() as sdk:
            for family, slug in FAMILY_SLUGS.items():
                with self.subTest(family=family):
                    signature = transport.configuration_signature(self.settings, family)
                    self.assertEqual(signature["transport_version"], "entry-level-skill-groups.v2")
                    self.assertEqual(signature["job_family"], family)
                    self.assertEqual(set(signature["branches"]), set(GROUPS))
                    for group in GROUPS:
                        branch = signature["branches"][group]
                        expected = bundle[family, group]
                        self.assertEqual(branch["agent_name"], f"careergps-entry-level-{slug}-{group}")
                        self.assertEqual(branch["agent_version"], "1")
                        self.assertEqual(branch["definition_sha256"], expected.definition_sha256)
                        self.assertEqual(branch["instructions_sha256"], expected.instructions_sha256)
                        self.assertEqual(branch["instructions_source"], "repository_bundle")
                        self.assertEqual(branch["schema_sha256"], digest(build_format(group, family)["schema"]))
            sdk.project_factory.assert_not_called()
            sdk.credential_factory.assert_not_called()

    def test_invalid_local_bundle_blocks_signature_and_preflight_before_azure(self):
        for operation in ("signature", "preflight"):
            with self.subTest(operation=operation), fake_saved_agents() as sdk, \
                    patch.object(transport, "load_bundle", side_effect=AgentBundleError("Changed local artifact")):
                with self.assertRaises(SkillGapConfigurationError) as caught:
                    if operation == "signature":
                        transport.configuration_signature(self.settings, "ai_engineer")
                    else:
                        transport.preflight(GROUPS, self.save, settings=self.settings, family="ai_engineer")
                self.assertEqual(caught.exception.code, "entry_level_bundle_invalid")
                sdk.project_factory.assert_not_called()
                sdk.credential_factory.assert_not_called()

    def test_preflight_verifies_exact_all_nine_saved_definitions_without_inference(self):
        bundle = load_bundle()
        for family in FAMILY_SLUGS:
            with self.subTest(family=family), fake_saved_agents() as sdk:
                prepared = transport.preflight(GROUPS, self.save, settings=self.settings, family=family)
                self.assertEqual(set(prepared), set(GROUPS))
                self.assertEqual(sdk.project.agents.get_version.call_args_list,
                                 [call(bundle[family, group].name, "1") for group in GROUPS])
                for group, item in prepared.items():
                    expected = bundle[family, group]
                    self.assertEqual((item.family, item.agent_name, item.agent_version),
                                     (family, expected.name, "1"))
                    self.assertEqual(item.definition, expected.definition)
                    check = self.saved[group, "configuration_check.json"]
                    self.assertEqual(check["model_calls"], 0)
                    self.assertEqual(check["instructions_sha256"], expected.instructions_sha256)
                    for field in ("pinned_version_match", "definition_match", "instructions_match",
                                  "schema_match", "model_match", "reasoning_match"):
                        self.assertTrue(check[field], field)
                self.assert_no_inference(sdk)

    def test_changed_remote_instructions_reject_before_inference(self):
        def mutate(saved):
            saved.definition["instructions"] += "Unreviewed instruction."

        with fake_saved_agents(mutate=mutate) as sdk:
            with self.assertRaises(SkillGapConfigurationError) as caught:
                transport.preflight(GROUPS, self.save, settings=self.settings, family="data_analyst")
            self.assertEqual(caught.exception.code, "foundation_entry_level_binding_mismatch")
            check = self.saved["foundation", "configuration_check.json"]
            self.assertFalse(check["definition_match"])
            self.assertFalse(check["instructions_match"])
            self.assertEqual(check["model_calls"], 0)
            self.assert_no_inference(sdk)

    def test_wrong_saved_version_and_draft_are_rejected(self):
        for values in ({"version": "2"}, {"draft": True}, {"draft": None, "is_draft": True}):
            def mutate(saved):
                for key, value in values.items():
                    setattr(saved, key, value)

            with self.subTest(values=values), fake_saved_agents(mutate=mutate) as sdk:
                with self.assertRaises(SkillGapConfigurationError) as caught:
                    transport.preflight(("systems",), self.save, settings=self.settings, family="software_engineer")
                self.assertEqual(caught.exception.code, "systems_entry_level_binding_mismatch")
                self.assertFalse(self.saved["systems", "configuration_check.json"]["pinned_version_match"])
                self.assert_no_inference(sdk)

    def test_remote_model_reasoning_and_schema_changes_are_rejected(self):
        for kind, check_field in (("model", "model_match"), ("reasoning", "reasoning_match"), ("schema", "schema_match")):
            def mutate(saved):
                if kind == "model":
                    saved.definition["model"] = "unreviewed-model"
                elif kind == "reasoning":
                    saved.definition["reasoning"]["effort"] = "low"
                else:
                    saved.definition["text"]["format"]["strict"] = False

            with self.subTest(kind=kind), fake_saved_agents(mutate=mutate) as sdk:
                with self.assertRaises(SkillGapConfigurationError) as caught:
                    transport.preflight(("lifecycle",), self.save, settings=self.settings, family="ai_engineer")
                self.assertEqual(caught.exception.code, "lifecycle_entry_level_binding_mismatch")
                self.assertFalse(self.saved["lifecycle", "configuration_check.json"][check_field])
                self.assert_no_inference(sdk)

    def test_unsupported_family_is_rejected_before_azure(self):
        with fake_saved_agents() as sdk:
            with self.assertRaises(SkillGapConfigurationError) as caught:
                transport.preflight(GROUPS, self.save, settings=self.settings, family="unsupported")
            self.assertEqual(caught.exception.code, "entry_level_family_unsupported")
            sdk.project_factory.assert_not_called()
            sdk.credential_factory.assert_not_called()

    def test_missing_endpoint_is_rejected_before_azure(self):
        with fake_saved_agents() as sdk:
            with self.assertRaises(SkillGapConfigurationError) as caught:
                transport.preflight(GROUPS, self.save, settings=SkillGapSettings(_env_file=None), family="ai_engineer")
            self.assertEqual(caught.exception.code, "foundation_agent_not_configured")
            sdk.project_factory.assert_not_called()
            sdk.credential_factory.assert_not_called()

    def test_unavailable_remote_agent_is_reported_without_inference(self):
        with fake_saved_agents(failure=RuntimeError("Offline fixture")) as sdk:
            with self.assertRaises(SkillGapConfigurationError) as caught:
                transport.preflight(("systems",), self.save, settings=self.settings, family="ai_engineer")
            self.assertEqual(caught.exception.code, "systems_entry_level_agent_unavailable")
            self.assert_no_inference(sdk)


if __name__ == "__main__":
    unittest.main()
