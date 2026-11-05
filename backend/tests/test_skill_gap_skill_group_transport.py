"""Offline checks for approved, scoped saved-Agent experiment contracts."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.services.skill_gaps import skill_group_transport as groups
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.core_cards import CoreSkillCards
from app.services.skill_gaps.skill_groups import absent_output, make_group_payloads
from app.services.skill_gaps.sources import build_sources
from app.services.skill_gaps.transport import SkillGapConfigurationError


def settings(**changes):
    return SimpleNamespace(**{
        "skill_gap_foundry_project_endpoint": "https://fixture.invalid/api/projects/private",
        **{f"skill_gap_{group}_agent_name": f"fixture-{group}" for group in groups.GROUPS},
        **{f"skill_gap_{group}_agent_version": str(i) for i, group in enumerate(groups.GROUPS, 1)},
        **changes,
    })


def payload(group, family="ai_engineer"):
    catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    full = {"task": "extract_resume_evidence", "job_family": family,
            "evidence_contract": "careergps_core_resume_evidence_v12",
            "resume_id": "fixture-resume", "core_skills": CoreSkillCards(catalog).for_family(family),
            "resume_sources": build_sources({
                "work_experience": [{"description": "Built a data service."}],
                "research_experience": [{"description": "Fine-tuned a model with LoRA."}],
                "technical_skills": ["Python", "Spark SQL"],
            })}
    return make_group_payloads(full)[group]


def definition(group):
    format_ = json.loads(groups.GROUP_FORMAT_PATHS[group].read_text(encoding="utf-8"))
    return {"model": "fixture-model", "reasoning": {"effort": "medium"},
            "instructions": groups.GROUP_INSTRUCTIONS_PATHS[group].read_text(encoding="utf-8"),
            "text": {"format": {"type": "json_schema", **format_}}}


def response(group="foundation", **changes):
    output = absent_output(payload(group))
    raw = {"agent_reference": {"name": f"fixture-{group}", "version": "7"},
           "text": {"format": {"type": "json_schema", "strict": True,
                                "name": f"careergps_core_group_{group}_v12"}}}
    fields = {"status": "completed", "output_text": json.dumps(output),
              "model_dump": lambda **kwargs: deepcopy(raw)}
    return SimpleNamespace(**{**fields, **changes})


@contextmanager
def fake_sdk(*, mutate=None, failure=None, latest_versions=None):
    modules = {name: ModuleType(name) for name in ("azure", "azure.ai", "azure.ai.projects", "azure.identity")}
    for name in ("azure", "azure.ai"):
        modules[name].__path__ = []
    modules["azure"].ai = modules["azure.ai"]
    modules["azure"].identity = modules["azure.identity"]
    modules["azure.ai"].projects = modules["azure.ai.projects"]
    credential, project, client = MagicMock(), MagicMock(), MagicMock()
    for context in (credential, project, client):
        context.__enter__.return_value = context
    factory, credential_factory = MagicMock(return_value=project), MagicMock(return_value=credential)
    modules["azure.identity"].DefaultAzureCredential = credential_factory
    modules["azure.ai.projects"].AIProjectClient = factory
    project.get_openai_client.return_value = client
    client.conversations.create.return_value = SimpleNamespace(id="fixture-conversation")
    client.responses.create.return_value = response()

    def get_version(name, version):
        if failure is not None:
            raise failure
        group = name.removeprefix("fixture-")
        value = SimpleNamespace(name=name, version=version, draft=False, definition=definition(group))
        if mutate is not None:
            mutate(group, value)
        return value

    project.agents.get_version.side_effect = get_version
    versions = ({"foundation": "7", "lifecycle": "8", "systems": "9"}
                if latest_versions is None else latest_versions)

    def list_versions(name, **kwargs):
        if failure is not None:
            raise failure
        version = versions.get(name.removeprefix("fixture-"))
        return [] if version is None else [get_version(name, version)]

    project.agents.list_versions.side_effect = list_versions
    with patch.dict(sys.modules, modules):
        yield SimpleNamespace(factory=factory, credential_factory=credential_factory,
                              project=project, client=client, latest_versions=versions)


class SkillGroupTransportTests(unittest.TestCase):
    def setUp(self):
        self.saved = {}

    def save(self, group, name, value):
        self.saved[group, name] = deepcopy(value)

    def test_signature_is_local_and_keeps_all_group_contract_hashes(self):
        with fake_sdk() as sdk:
            value = groups.configuration_signature(SimpleNamespace())
        self.assertEqual(set(value["branches"]), set(groups.GROUPS))
        self.assertTrue(all(binding["agent_version"] == "latest" and binding["agent_name"] is None
                            and len(binding["instructions_sha256"]) == 64
                            and len(binding["schema_sha256"]) == 64
                            for binding in value["branches"].values()))
        self.assertEqual(len({v["schema_name"] for v in value["branches"].values()}), 3)
        sdk.factory.assert_not_called()
        sdk.credential_factory.assert_not_called()

    def test_configuration_signature_changes_only_affected_group_binding(self):
        initial = groups.configuration_signature(settings())
        changed = groups.configuration_signature(settings(skill_gap_systems_agent_version="10"))
        self.assertNotEqual(initial["branches"]["systems"], changed["branches"]["systems"])
        self.assertEqual(initial["branches"]["foundation"], changed["branches"]["foundation"])

    def test_missing_binding_fails_before_any_sdk_client(self):
        with fake_sdk() as sdk, self.assertRaises(SkillGapConfigurationError) as error:
            groups.preflight(groups.GROUPS, self.save, settings=settings(skill_gap_systems_agent_name=None))
        self.assertEqual(error.exception.code, "systems_agent_not_configured")
        sdk.factory.assert_not_called()
        self.assertEqual(self.saved["systems", "configuration_check.json"]["model_calls"], 0)

    def test_invalid_saved_pins_fail_without_network(self):
        for version in ("0", "01", "-1", "draft", "1.5", 3):
            with self.subTest(version=version), fake_sdk() as sdk:
                with self.assertRaises(SkillGapConfigurationError) as error:
                    groups.preflight(("foundation",), self.save,
                        settings=settings(skill_gap_foundation_agent_version=version))
                self.assertEqual(error.exception.code, "foundation_agent_version_unavailable")
                sdk.factory.assert_not_called()

    def test_latest_is_resolved_to_checked_numeric_pin_without_inference(self):
        for version in (None, "", "latest", " LATEST "):
            with self.subTest(version=version), fake_sdk() as sdk:
                configured = settings(skill_gap_foundation_agent_version=version)
                self.assertTrue(groups.uses_latest(configured))
                prepared = groups.preflight(("foundation",), self.save, settings=configured)["foundation"]
                self.assertEqual(prepared.agent_version, "7")
                sdk.project.agents.list_versions.assert_called_once_with(
                    "fixture-foundation", limit=1, order="desc", include_drafts=False)
                sdk.project.agents.get_version.assert_not_called()
                sdk.project.get_openai_client.assert_not_called()
                sdk.client.responses.create.assert_not_called()
                self.assertTrue(prepared.configuration_check["reasoning_match"])
                self.assertIsNotNone(prepared.configuration_check["instructions_file_sha256"])
        self.assertFalse(groups.uses_latest(settings()))

    def test_exact_pins_and_all_saved_contracts_checked_before_inference(self):
        with fake_sdk() as sdk:
            prepared = groups.preflight(groups.GROUPS, self.save, settings=settings())
        self.assertEqual(set(prepared), set(groups.GROUPS))
        self.assertEqual([tuple(call.args) for call in sdk.project.agents.get_version.call_args_list],
                         [(f"fixture-{group}", str(i)) for i, group in enumerate(groups.GROUPS, 1)])
        sdk.project.agents.list_versions.assert_not_called()
        sdk.project.get_openai_client.assert_not_called()

    def test_latest_cannot_silently_adopt_new_instructions_or_lower_reasoning(self):
        for field, code in (("instructions", "instructions_mismatch"), ("reasoning", "reasoning_mismatch")):
            def mutate(group, value):
                if field == "instructions":
                    value.definition[field] = "A different saved prompt"
                else:
                    value.definition[field]["effort"] = "low"
            with self.subTest(field=field), fake_sdk(mutate=mutate) as sdk:
                with self.assertRaises(SkillGapConfigurationError) as error:
                    groups.preflight(("foundation",), self.save,
                        settings=settings(skill_gap_foundation_agent_version="latest"))
                self.assertEqual(error.exception.code, "foundation_" + code)
                sdk.client.responses.create.assert_not_called()

    def test_numeric_pin_also_requires_medium(self):
        def mutate(group, value):
            value.definition["reasoning"]["effort"] = "low"
        with fake_sdk(mutate=mutate) as sdk, self.assertRaises(SkillGapConfigurationError) as error:
            groups.preflight(("foundation",), self.save, settings=settings())
        self.assertEqual(error.exception.code, "foundation_reasoning_mismatch")
        sdk.project.get_openai_client.assert_not_called()

    def test_last_group_contract_mismatch_prevents_all_inference(self):
        for field in ("schema", "name", "strict", "instructions"):
            def mutate(group, value):
                if group == "systems":
                    if field == "instructions":
                        value.definition["instructions"] = "Wrong approved prompt"
                    else:
                        value.definition["text"]["format"][field] = {
                            "schema": {}, "name": "careergps_core_resume_evidence_v12", "strict": False,
                        }[field]
            with self.subTest(field=field), fake_sdk(mutate=mutate) as sdk:
                with self.assertRaises(SkillGapConfigurationError):
                    groups.preflight(groups.GROUPS, self.save, settings=settings())
                self.assertEqual(sdk.project.agents.get_version.call_count, 3)
                sdk.client.responses.create.assert_not_called()

    def test_generated_local_schema_drift_fails_before_sdk(self):
        original = Path.read_bytes
        def changed(path):
            if path == groups.GROUP_FORMAT_PATHS["foundation"]:
                return b'{"name":"stale","schema":{},"strict":true}'
            return original(path)
        with fake_sdk() as sdk, patch.object(Path, "read_bytes", new=changed):
            with self.assertRaises(SkillGapConfigurationError) as error:
                groups.preflight(("foundation",), self.save, settings=settings())
        self.assertEqual(error.exception.code, "foundation_local_contract_unavailable")
        sdk.factory.assert_not_called()

    def test_draft_empty_latest_bad_version_and_wrong_name_are_rejected(self):
        for attribute, value, code in (("draft", True, "agent_draft"),
                                        ("version", "latest", "agent_version_mismatch"),
                                        ("name", "another-agent", "agent_name_mismatch")):
            def mutate(group, saved):
                setattr(saved, attribute, value)
            with self.subTest(attribute=attribute), fake_sdk(mutate=mutate) as sdk:
                with self.assertRaises(SkillGapConfigurationError) as error:
                    groups.preflight(("foundation",), self.save,
                        settings=settings(skill_gap_foundation_agent_version="latest"))
                self.assertEqual(error.exception.code, "foundation_" + code)
                sdk.client.responses.create.assert_not_called()
        with fake_sdk(latest_versions={}) as sdk, self.assertRaises(SkillGapConfigurationError) as error:
            groups.preflight(("foundation",), self.save,
                settings=settings(skill_gap_foundation_agent_version="latest"))
        self.assertEqual(error.exception.code, "foundation_agent_version_unavailable")

    def test_sdk_failure_does_not_expose_private_details(self):
        with fake_sdk(failure=RuntimeError("secret-fixture private.invalid")):
            with self.assertRaises(SkillGapConfigurationError) as error:
                groups.preflight(("lifecycle",), self.save, settings=settings())
        self.assertEqual(error.exception.code, "lifecycle_agent_unavailable")
        self.assertNotIn("secret-fixture", error.exception.public_message)
        self.assertNotIn("private.invalid", error.exception.public_message)

    def test_invoke_uses_actual_pin_once_and_decodes_internal_group_schema(self):
        for group in groups.GROUPS:
            requested, saved = [], {}
            with self.subTest(group=group), fake_sdk() as sdk:
                sdk.client.responses.create.return_value = response(group)
                configured = settings(**{f"skill_gap_{group}_agent_version": "latest"})
                prepared = groups.preflight((group,), self.save, settings=configured)[group]
                old_pin = prepared.agent_version
                sdk.latest_versions[group] = "99"
                output = groups.invoke_prepared(prepared, payload(group), saved.__setitem__,
                                                lambda: requested.append(1), {})
                self.assertEqual(output, absent_output(payload(group)))
                self.assertEqual(requested, [1])
                self.assertEqual(sdk.project.agents.list_versions.call_count, 1)
                self.assertEqual(sdk.client.responses.create.call_args.kwargs["extra_body"]["agent_reference"],
                                 {"type": "agent_reference", "name": f"fixture-{group}", "version": old_pin})
                sdk.client.responses.create.assert_called_once()
                sdk.project.get_openai_client.assert_called_once_with(timeout=480, max_retries=0)
                sdk.client.conversations.delete.assert_called_once_with(conversation_id="fixture-conversation")
                self.assertIn("agent.raw.json", saved)

    def test_input_scope_and_core_card_mismatch_fail_before_model_or_client(self):
        mutations = [
            lambda p: p["evidence_scope"].update(branch="systems"),
            lambda p: p["evidence_scope"].update(partition_policy_version="section-scope"),
            lambda p: p["evidence_scope"].update(assigned_skill_ids=[]),
            lambda p: p["evidence_scope"].update(activity_ids=[]),
            lambda p: p["core_skills"].pop(),
            lambda p: p["core_skills"][0].update(definition="Changed rule"),
            lambda p: p["resume_sources"][0].update(path="/personal_information"),
        ]
        with fake_sdk() as sdk:
            prepared = groups.preflight(("foundation",), self.save, settings=settings())["foundation"]
            for mutate in mutations:
                p = payload("foundation")
                mutate(p)
                with self.subTest(mutation=mutate), self.assertRaises(SkillGapConfigurationError) as error:
                    groups.invoke_prepared(prepared, p, lambda *args: None,
                        lambda: self.fail("Unexpected model call"), {})
                self.assertEqual(error.exception.code, "foundation_scope_mismatch")
            sdk.project.get_openai_client.assert_not_called()
            sdk.client.responses.create.assert_not_called()

    def test_all_three_families_use_ordered_catalog_cards(self):
        with fake_sdk() as sdk:
            prepared = groups.preflight(("foundation",), self.save, settings=settings())["foundation"]
            for family in ("software_engineer", "data_analyst", "ai_engineer"):
                groups._validate_scope("foundation", payload("foundation", family),
                    json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8")))
            sdk.client.responses.create.assert_not_called()
        self.assertTrue(prepared.configuration_check["schema_match"])

    def test_changed_prompt_or_prepared_definition_fails_before_inference(self):
        with fake_sdk() as sdk:
            prepared = groups.preflight(("foundation",), self.save, settings=settings())["foundation"]
            original = Path.read_bytes
            def changed(path):
                if path == groups.GROUP_INSTRUCTIONS_PATHS["foundation"]:
                    return original(path) + b"\nChanged after preflight"
                return original(path)
            with patch.object(Path, "read_bytes", new=changed):
                with self.assertRaises(SkillGapConfigurationError) as error:
                    groups.invoke_prepared(prepared, payload("foundation"), lambda *args: None,
                                           lambda: self.fail("Unexpected model call"), {})
                self.assertEqual(error.exception.code, "foundation_local_contract_changed")
            prepared.definition["model"] = "Changed after preflight"
            with self.assertRaises(SkillGapConfigurationError) as error:
                groups.invoke_prepared(prepared, payload("foundation"), lambda *args: None,
                                       lambda: self.fail("Unexpected model call"), {})
            self.assertEqual(error.exception.code, "foundation_prepared_configuration_changed")
            sdk.client.responses.create.assert_not_called()

    def test_wrong_response_format_or_incomplete_response_is_not_retried(self):
        wrong = response(model_dump=lambda **kwargs: {
            "text": {"format": {"type": "json_schema", "strict": True,
                                "name": "careergps_core_resume_evidence_v12"}}})
        for returned in (wrong, response(status="incomplete")):
            saved, requested = {}, []
            with self.subTest(response=returned), fake_sdk() as sdk:
                prepared = groups.preflight(("foundation",), self.save, settings=settings())["foundation"]
                sdk.client.responses.create.return_value = returned
                with self.assertRaises(SkillGapConfigurationError) as error:
                    groups.invoke_prepared(prepared, payload("foundation"), saved.__setitem__,
                                           lambda: requested.append(1), {})
                self.assertEqual(error.exception.code, "foundation_inference_failed")
                self.assertEqual(requested, [1])
                sdk.client.responses.create.assert_called_once()
                self.assertIn("agent.raw.json", saved)

    def test_resolved_signature_tracks_real_versions_without_mutating_configuration(self):
        configured = settings(skill_gap_foundation_agent_version="latest")
        original = groups.configuration_signature(configured)
        with fake_sdk() as sdk:
            prepared = groups.preflight(("foundation",), self.save, settings=configured)
            signature = groups.resolved_configuration_signature(configured, prepared)
            sdk.latest_versions["foundation"] = "10"
            newer = groups.resolved_configuration_signature(configured,
                groups.preflight(("foundation",), self.save, settings=configured))
        self.assertEqual(groups.configuration_signature(configured), original)
        self.assertEqual(signature["branches"]["foundation"]["agent_version"], "7")
        self.assertNotEqual(signature, newer)
        self.assertEqual(signature["branches"]["lifecycle"], original["branches"]["lifecycle"])


if __name__ == "__main__":
    unittest.main()
