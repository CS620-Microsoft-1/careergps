"""Skill-group orchestration with synthetic snapshots and no network/database."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Lock
import unittest
from unittest.mock import patch
from uuid import UUID

from app.core.config import SkillGapSettings
from app.services.skill_gaps.runs import SkillGapRunManager
from app.services.skill_gaps.skill_group_transport import PreparedGroup
from app.services.skill_gaps.skill_groups import GROUPS
from app.services.skill_gaps import skill_group_transport
from app.services.skill_gaps.transport import SkillGapConfigurationError
from tests.skill_gap_fixtures import (
    CONFIRMED_AT, RESUME_ID, USER_ID, absent_response, reviewed_resume,
)
from tests.test_skill_gap_run_ownership import wait_for


def settings(**changes):
    values = {
        "skill_gap_foundry_project_endpoint": "https://fixture.invalid/api/projects/test",
        **{f"skill_gap_{group}_agent_name": f"fixture-{group}" for group in GROUPS},
        **{f"skill_gap_{group}_agent_version": "1" for group in GROUPS},
    }
    values.update(changes)
    return SkillGapSettings(_env_file=None, **values)


class SkillGroupRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.managers, self.calls, self.preflights = [], [], []
        self.lock = Lock()
        self.network = patch("socket.socket", side_effect=AssertionError("No network allowed"))
        self.network.start()

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.network.stop()
        self.temp.cleanup()

    def preflight(self, groups, save, *, settings):
        self.preflights.append(tuple(groups))
        return {group: group for group in groups}

    def invoke(self, group, payload, save, on_request, timings):
        on_request()
        with self.lock:
            self.calls.append((group, deepcopy(payload)))
        save("agent.raw.json", {"group": group})
        return absent_response(payload)

    def manager(self, **changes):
        options = dict(settings=settings(), group_preflight=self.preflight, group_invoker=self.invoke)
        options.update(changes)
        manager = SkillGapRunManager(self.directory, **options)
        self.managers.append(manager)
        return manager

    def submit(self, manager, **changes):
        values = dict(user_id=USER_ID, resume_id=RESUME_ID, reviewed_resume=reviewed_resume(),
                      filename="fixture.pdf", confirmed_at=CONFIRMED_AT, job_family="ai_engineer")
        values.update(changes)
        return manager.submit(**values)

    def complete(self, manager, **changes):
        result = wait_for(manager, self.submit(manager, **changes))
        self.assertEqual(result.status, "completed", result.error)
        return result

    def artifact(self, result, name):
        return json.loads((self.directory / result.id / name).read_text(encoding="utf-8"))

    def test_three_groups_run_concurrently_read_all_sources_and_return_only_owned_skills(self):
        barrier = Barrier(3)

        def concurrent(*args):
            barrier.wait(timeout=3)
            return self.invoke(*args)

        manager = self.manager(group_invoker=concurrent)
        result = self.complete(manager)
        self.assertEqual(result.model_calls, 3)
        self.assertEqual(self.preflights, [GROUPS])
        original = self.artifact(result, "input.json")
        self.assertCountEqual([group for group, _ in self.calls], GROUPS)
        self.assertEqual([len(next(p for g, p in self.calls if g == group)["core_skills"])
                          for group in GROUPS], [8, 8, 7])
        assigned = []
        for group, payload in self.calls:
            self.assertEqual(payload["resume_sources"], original["resume_sources"])
            owned = [card["skill_id"] for card in payload["core_skills"]]
            self.assertEqual(payload["evidence_scope"]["assigned_skill_ids"], owned)
            assigned.extend(owned)
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertCountEqual(assigned, [card["skill_id"] for card in original["core_skills"]])
        self.assertEqual(len(result.report["skills"]), 23)
        self.assertEqual(self.artifact(result, "run.json")["extraction_strategy"], "skill_groups")

    def test_same_snapshot_reuses_report_but_force_runs_every_group_again(self):
        manager = self.manager()
        first = self.complete(manager)
        cached = self.submit(manager)
        self.assertEqual(cached.id, first.id)
        self.assertTrue(cached.reused)
        second = self.complete(manager, force=True)
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(second.model_calls, 3)
        self.assertEqual(len(self.calls), 6)

    def test_rebuild_from_group_cache_preserves_all_scores_without_new_calls(self):
        manager = self.manager()
        first = self.complete(manager)
        second = self.complete(manager, rebuild_report=True)
        self.assertEqual(second.model_calls, 0)
        self.assertEqual(first.report["skills"], second.report["skills"])
        self.assertTrue(all(node["cache_hit"] for node in self.artifact(second, "status.json")["branches"].values()))

    def test_changing_any_source_invalidates_all_groups_and_owner_isolation_is_preserved(self):
        manager = self.manager()
        self.complete(manager)
        changed = reviewed_resume()
        changed["projects"][0]["content"].append("Compared an additional configuration.")
        second = self.complete(manager, reviewed_resume=changed)
        self.assertEqual(second.model_calls, 3)
        third = self.complete(manager, reviewed_resume=changed,
            user_id=UUID("33333333-3333-4333-8333-333333333333"))
        self.assertEqual(third.model_calls, 3)

    def test_invalid_record_only_blocks_its_owned_skill(self):
        def invalid(group, payload, *args):
            result = self.invoke(group, payload, *args)
            if group == "lifecycle":
                result["result"]["fine_tuning"] = {
                    "kind": "knowledge", "evidence_id": "not-a-source-id"}
            return result

        result = self.complete(self.manager(group_invoker=invalid))
        self.assertEqual(result.report["unscored_skill_ids"], ["fine_tuning"])
        self.assertEqual(len(result.report["skills"]), 23)

    def test_preflight_failure_never_falls_back_to_old_agents(self):
        def unavailable(*args, **kwargs):
            raise SkillGapConfigurationError("systems_schema_mismatch", "Wrong internal Schema.")

        fallback = []
        manager = self.manager(group_preflight=unavailable)
        result = wait_for(manager, self.submit(manager))
        self.assertEqual((result.status, result.model_calls), ("failed", 0))
        self.assertEqual(self.calls, [])

    def test_all_supported_families_keep_their_complete_public_skill_sets(self):
        manager = self.manager()
        for family, count in [("software_engineer", 22), ("data_analyst", 18), ("ai_engineer", 23)]:
            result = self.complete(manager, job_family=family)
            self.assertEqual((result.model_calls, len(result.report["skills"])), (3, count))

    def test_empty_resume_needs_no_agent_call(self):
        result = self.complete(self.manager(), reviewed_resume={})
        self.assertEqual((result.model_calls, self.calls, self.preflights), (0, [], []))

    def test_latest_versions_are_run_scoped_and_only_changed_group_reextracts(self):
        versions = {group: "1" for group in GROUPS}

        def prepared(groups, save, *, settings):
            result = {}
            for group in groups:
                instructions, format_, prompt_hash, schema_hash, _ = skill_group_transport._load_local_contract(group)
                definition = {"kind": "prompt", "model": "fixture-model",
                    "reasoning": {"effort": "medium"}, "instructions": instructions,
                    "text": {"format": {"type": "json_schema", **format_}}}
                check = skill_group_transport._check_definition(group, definition, versions[group],
                    instructions, format_, save, instructions_hash=prompt_hash, schema_file_hash=schema_hash)
                result[group] = PreparedGroup(group, settings.skill_gap_foundry_project_endpoint,
                    getattr(settings, f"skill_gap_{group}_agent_name"), versions[group], definition, check)
            return result

        actual = []

        def invoke(prepared, *args):
            actual.append((prepared.branch, prepared.agent_version))
            return self.invoke(prepared.branch, *args)

        manager = self.manager(settings=settings(**{f"skill_gap_{g}_agent_version": "latest" for g in GROUPS}),
            group_preflight=prepared, group_invoker=invoke)
        first = self.complete(manager)
        self.assertTrue(self.submit(manager).reused)
        versions["foundation"] = "2"
        second = self.complete(manager)
        self.assertEqual(second.model_calls, 1)
        self.assertCountEqual(actual, [(g, "1") for g in GROUPS] + [("foundation", "2")])
        old = self.artifact(first, "run.json")["branch_configuration"]["branches"]
        new = self.artifact(second, "run.json")["branch_configuration"]["branches"]
        self.assertEqual(old["foundation"]["agent_version"], "1")
        self.assertEqual(new["foundation"]["agent_version"], "2")
        self.assertEqual(old["lifecycle"], new["lifecycle"])


if __name__ == "__main__":
    unittest.main()
