"""Verify the shipped nine-Agent bundle and management operations without Azure."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from azure.core.exceptions import ResourceNotFoundError

from app.services.skill_gaps.entry_level import build_format
from app.services.skill_gaps.entry_level_agents import (
    AgentBundleError, BUNDLE_ROOT, FAMILY_SLUGS, digest, load_bundle, manage_agents, verify_saved_agent,
)
from scripts.manage_entry_level_agents import main


class FakeAgents:
    def __init__(self, bundle, *, existing=False):
        self.saved = {}
        self.names = set()
        self.created = []
        self.reads = []
        if existing:
            for item in bundle.values():
                self.saved[item.name, item.version] = SimpleNamespace(
                    name=item.name, version=item.version, draft=False, definition=deepcopy(item.definition))
                self.names.add(item.name)

    def get_version(self, name, version):
        self.reads.append((name, version))
        if (name, version) not in self.saved:
            raise ResourceNotFoundError("Missing test Agent")
        return self.saved[name, version]

    def get(self, name):
        if name not in self.names:
            raise ResourceNotFoundError("Missing test Agent name")
        return SimpleNamespace(name=name)

    def create_version(self, name, *, body):
        if name in self.names:
            raise AssertionError("Tests must never append to an existing Agent name")
        self.created.append((name, deepcopy(body)))
        self.names.add(name)
        saved = SimpleNamespace(name=name, version="1", draft=False, definition=deepcopy(body["definition"]))
        self.saved[name, "1"] = saved
        return saved


class EntryLevelAgentBundleTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "bundle"
        shutil.copytree(BUNDLE_ROOT, self.root)

    def manifest(self):
        return json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))

    def save_manifest(self, manifest):
        (self.root / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))

    def test_all_nine_exact_definitions_and_formats_are_reconstructible(self):
        bundle = load_bundle(self.root)
        self.assertEqual(len(bundle), 9)
        self.assertEqual({family for family, _ in bundle}, set(FAMILY_SLUGS))
        for (family, group), item in bundle.items():
            with self.subTest(family=family, group=group):
                self.assertEqual(item.name, f"careergps-entry-level-{FAMILY_SLUGS[family]}-{group}")
                self.assertEqual(item.version, "1")
                self.assertEqual(digest(item.definition), item.definition_sha256)
                self.assertEqual(hashlib.sha256(item.instructions_path.read_bytes()).hexdigest(), item.instructions_sha256)
                self.assertEqual(item.definition["text"]["format"], {"type": "json_schema", **build_format(group, family)})
                self.assertEqual(item.definition["model"], "gpt-6-luna")
                self.assertEqual(item.definition["reasoning"], {"effort": "medium"})
                self.assertEqual(item.definition["tools"], [])

    def test_software_systems_uses_hash_of_exact_source_instructions(self):
        item = load_bundle(self.root)["software_engineer", "systems"]
        self.assertEqual(item.instructions_sha256,
                         "318f39542c75a7c0cea08ef3f1bfb4ef9ee149e0a20deeb9a72b7a45049ce586")
        self.assertEqual(item.definition_sha256,
                         "e2e5e112323b076d853e0dc346d37a1a6276dea9a3a4589ea56fea9d037fd0d5")

    def test_instruction_changes_are_rejected(self):
        item = load_bundle(self.root)["ai_engineer", "foundation"]
        item.instructions_path.write_bytes(item.instructions_path.read_bytes() + b"changed")
        with self.assertRaisesRegex(AgentBundleError, "instructions hash mismatch"):
            load_bundle(self.root)

    def test_missing_artifact_is_rejected(self):
        item = load_bundle(self.root)["data_analyst", "lifecycle"]
        item.response_format_path.unlink()
        with self.assertRaisesRegex(AgentBundleError, "Missing Agent artifact"):
            load_bundle(self.root)

    def test_artifact_path_cannot_escape_bundle(self):
        manifest = self.manifest()
        manifest["agents"]["ai_engineer"]["foundation"]["instructions"] = "../outside.txt"
        self.save_manifest(manifest)
        with self.assertRaisesRegex(AgentBundleError, "stay inside the bundle"):
            load_bundle(self.root)

    def test_missing_or_extra_family_and_group_are_rejected(self):
        for scope, key in (("family", "extra_family"), ("group", "extra_group")):
            with self.subTest(scope=scope):
                manifest = self.manifest()
                if scope == "family":
                    manifest["agents"][key] = {}
                else:
                    manifest["agents"]["ai_engineer"][key] = {}
                self.save_manifest(manifest)
                with self.assertRaisesRegex(AgentBundleError, "missing or unexpected fields"):
                    load_bundle(self.root)
                if scope == "family":
                    del manifest["agents"][key]
                else:
                    del manifest["agents"]["ai_engineer"][key]
                self.save_manifest(manifest)
        manifest = self.manifest()
        del manifest["agents"]["data_analyst"]["systems"]
        self.save_manifest(manifest)
        with self.assertRaisesRegex(AgentBundleError, "missing or unexpected fields"):
            load_bundle(self.root)

    def test_malformed_manifest_and_duplicate_keys_are_rejected(self):
        for text in ("{", '{"bundle_version":"one","bundle_version":"two"}'):
            with self.subTest(text=text):
                (self.root / "manifest.json").write_bytes(text.encode("utf-8"))
                with self.assertRaisesRegex(AgentBundleError, "valid JSON"):
                    load_bundle(self.root)

    def test_schema_drift_is_rejected_even_with_updated_artifact_hash(self):
        manifest = self.manifest()
        item = manifest["agents"]["software_engineer"]["foundation"]
        path = self.root / item["response_format"]
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["strict"] = False
        path.write_bytes(json.dumps(changed).encode("utf-8"))
        item["response_format_sha256"] = digest(changed)
        self.save_manifest(manifest)
        with self.assertRaisesRegex(AgentBundleError, "differs from the production schema"):
            load_bundle(self.root)

    def test_definition_options_cannot_change_model_reasoning_or_tools(self):
        original = self.manifest()
        for key, value in (("model", "other-model"), ("reasoning", {"effort": "low"}), ("tools", [{"type": "web_search"}])):
            with self.subTest(field=key):
                manifest = deepcopy(original)
                manifest["agents"]["ai_engineer"]["systems"]["definition_options"][key] = value
                self.save_manifest(manifest)
                with self.assertRaisesRegex(AgentBundleError, "reviewed policy"):
                    load_bundle(self.root)

    def test_complete_definition_and_source_hash_must_match(self):
        manifest = self.manifest()
        item = manifest["agents"]["data_analyst"]["systems"]
        item["definition_sha256"] = "0" * 64
        item["source"]["definition_sha256"] = "0" * 64
        self.save_manifest(manifest)
        with self.assertRaisesRegex(AgentBundleError, "complete definition hash mismatch"):
            load_bundle(self.root)

    def test_new_name_and_version_are_explicitly_pinned(self):
        manifest = self.manifest()
        manifest["agents"]["ai_engineer"]["foundation"]["version"] = "latest"
        self.save_manifest(manifest)
        with self.assertRaisesRegex(AgentBundleError, "pinned version 1"):
            load_bundle(self.root)

    def test_check_cli_never_creates_azure_client(self):
        output = StringIO()
        with patch("azure.ai.projects.AIProjectClient", side_effect=AssertionError("Unexpected Azure call")), redirect_stdout(output):
            code = main(["check", "--bundle", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["agent_count"], 9)

    def test_invalid_endpoint_fails_before_azure_access(self):
        with patch("azure.ai.projects.AIProjectClient", side_effect=AssertionError("Unexpected Azure call")), redirect_stderr(StringIO()):
            self.assertEqual(main(["verify", "--bundle", str(self.root), "--endpoint", "http://fixture.invalid"]), 1)


class EntryLevelAgentManagementTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_bundle()

    def test_create_builds_all_nine_and_second_run_reuses_exact_versions(self):
        agents = FakeAgents(self.bundle)
        client = SimpleNamespace(agents=agents)
        first = manage_agents(client, self.bundle, create=True)
        second = manage_agents(client, self.bundle, create=True)
        self.assertEqual(len(agents.created), 9)
        self.assertEqual({row["action"] for row in first}, {"created"})
        self.assertEqual({row["action"] for row in second}, {"verified"})
        for name, body in agents.created:
            self.assertEqual(body["metadata"]["scope"], "careergps-production")
            self.assertEqual(body["definition"], next(x.definition for x in self.bundle.values() if x.name == name))

    def test_verify_reads_all_nine_without_creating(self):
        agents = FakeAgents(self.bundle, existing=True)
        result = manage_agents(SimpleNamespace(agents=agents), self.bundle)
        self.assertEqual(len(result), 9)
        self.assertEqual(agents.created, [])

    def test_verify_missing_agent_never_creates(self):
        agents = FakeAgents(self.bundle)
        with self.assertRaisesRegex(AgentBundleError, "Missing Agent"):
            manage_agents(SimpleNamespace(agents=agents), self.bundle)
        self.assertEqual(agents.created, [])

    def test_existing_definition_mismatch_blocks_all_creations(self):
        agents = FakeAgents(self.bundle, existing=True)
        entries = list(self.bundle.values())
        first, last = entries[0], entries[-1]
        del agents.saved[first.name, first.version]
        agents.names.remove(first.name)
        agents.saved[last.name, last.version].definition["instructions"] += "changed"
        with self.assertRaisesRegex(AgentBundleError, "differs from the reviewed bundle"):
            manage_agents(SimpleNamespace(agents=agents), self.bundle, create=True)
        self.assertEqual(agents.created, [])

    def test_existing_name_without_pinned_version_is_not_overwritten(self):
        agents = FakeAgents(self.bundle)
        agents.names.add(next(iter(self.bundle.values())).name)
        with self.assertRaisesRegex(AgentBundleError, "already exists without its approved version"):
            manage_agents(SimpleNamespace(agents=agents), self.bundle, create=True)
        self.assertEqual(agents.created, [])

    def test_saved_draft_or_wrong_version_is_rejected(self):
        expected = next(iter(self.bundle.values()))
        for changes in ({"version": "2"}, {"draft": True}, {"name": "unrelated-agent"}):
            with self.subTest(changes=changes):
                saved = {"name": expected.name, "version": expected.version, "draft": False,
                         "definition": deepcopy(expected.definition), **changes}
                with self.assertRaisesRegex(AgentBundleError, "differs from the reviewed bundle"):
                    verify_saved_agent(saved, expected)

    def test_changed_in_memory_definition_is_rejected_before_remote_calls(self):
        agents = FakeAgents(self.bundle)
        next(iter(self.bundle.values())).definition["model"] = "unreviewed-model"
        with self.assertRaisesRegex(AgentBundleError, "changed after bundle validation"):
            manage_agents(SimpleNamespace(agents=agents), self.bundle, create=True)
        self.assertEqual(agents.reads, [])
        self.assertEqual(agents.created, [])


if __name__ == "__main__":
    unittest.main()
