"""Exercise the revised workflow through the normal Skill Gap run manager."""

from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.core.config import SkillGapSettings
from app.services.skill_gaps import entry_level, entry_level_transport, runs
from app.services.skill_gaps.skill_groups import GROUPS
from tests.skill_gap_fixtures import CONFIRMED_AT, RESUME_ID, USER_ID, group_manager, reviewed_resume


class EntryLevelRunTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.settings = SkillGapSettings(_env_file=None,
            skill_gap_foundry_project_endpoint="https://fixture.invalid/api/projects/test")
        self.calls = []
        self.preflights = []
        self.missing_proof = False

    def preflight(self, groups, save, *, settings, family):
        self.preflights.append((family, tuple(groups)))
        return {group: SimpleNamespace(branch=group) for group in groups}

    def invoke(self, prepared, payload, _save, on_request, _timings):
        on_request()
        group = prepared.branch
        self.calls.append((payload["job_family"], group))
        output = entry_level.absent_group_output(payload)
        if self.missing_proof and group == "foundation":
            output["result"]["programming"]["criteria"][0].update(
                status="supported", basis="practice", proof_ids=["p1"])
        return output

    def manager(self):
        instance = runs.SkillGapRunManager(self.root, settings=self.settings,
            group_preflight=self.preflight, group_invoker=self.invoke, entry_level_workflow=True)
        self.addCleanup(instance.close)
        return instance

    def submit(self, manager, *, family="software_engineer", resume=None, **kwargs):
        data = reviewed_resume() if resume is None else resume
        return manager.submit(user_id=USER_ID, resume_id=RESUME_ID, reviewed_resume=data,
            filename="example.pdf", confirmed_at=CONFIRMED_AT, job_family=family, **kwargs)

    def completed(self, manager, run):
        deadline = monotonic() + 10
        while monotonic() < deadline:
            view = manager.get(run.id, user_id=USER_ID)
            if view.status in ("completed", "failed"):
                self.assertEqual(view.status, "completed", view.error)
                return view
            sleep(.01)
        self.fail("Skill Gap run did not finish")

    def test_each_family_uses_its_pinned_groups_and_preserves_report_contract(self):
        manager = self.manager()
        for family, count in (("software_engineer", 22), ("data_analyst", 18), ("ai_engineer", 23)):
            with self.subTest(family=family):
                result = self.completed(manager, self.submit(manager, family=family))
                self.assertEqual(result.model_calls, 3)
                self.assertEqual(len(result.report["skills"]), count)
                self.assertEqual(result.report["job_family"], family)
                self.assertEqual(result.report["policy_version"], runs.ENTRY_LEVEL_POLICY)
                state = manager._states[result.id]
                self.assertEqual(state["branch_configuration"]["job_family"], family)
                self.assertEqual(state["extraction_strategy"], "skill_groups")
                self.assertCountEqual([g for f, g in self.calls if f == family], GROUPS)
                self.assertTrue(self.submit(manager, family=family).reused)

    def test_missing_proof_withholds_only_its_consumer_and_can_complete(self):
        self.missing_proof = True
        manager = self.manager()
        result = self.completed(manager, self.submit(manager))
        rows = {row["skill_id"]: row for row in result.report["skills"]}
        self.assertIsNotNone(result.match)
        self.assertIsNone(rows["programming"]["resume_evidence_strength"])
        self.assertIn("unknown_proof_id", {e["code"] for e in rows["programming"]["local_reference_check"]["errors"]})
        self.assertGreater(result.match.scored_skill_count, 0)
        self.assertFalse(manager._states[result.id]["branches"]["foundation"]["cache_stored"])

    def test_exact_branch_cache_and_force_keep_existing_run_controls(self):
        manager = self.manager()
        first = self.completed(manager, self.submit(manager))
        second = self.completed(manager, self.submit(manager, rebuild_report=True))
        third = self.completed(manager, self.submit(manager, force=True))
        self.assertEqual((first.model_calls, second.model_calls, third.model_calls), (3, 0, 3))
        self.assertEqual(first.report, second.report)

    def test_legacy_report_remains_readable_under_new_workflow(self):
        with TemporaryDirectory() as temp:
            legacy_manager = group_manager(Path(temp))
            try:
                legacy = self.completed(legacy_manager, self.submit(legacy_manager))
            finally:
                legacy_manager.close()
            self.root = Path(temp)
            manager = self.manager()
            arguments = {"user_id": USER_ID, "resume_id": RESUME_ID, "reviewed_resume": reviewed_resume(),
                         "job_family": "software_engineer"}
            self.assertEqual(manager.latest(**arguments).id, legacy.id)
            self.assertEqual(manager.get(legacy.id, user_id=USER_ID).report, legacy.report)
            with self.assertRaises(KeyError):
                manager.latest(**{**arguments, "user_id": uuid4()})
            revised = self.completed(manager, self.submit(manager))
            self.assertNotEqual(revised.id, legacy.id)
            self.assertEqual(manager.latest(**arguments).id, revised.id)

    def test_empty_resume_completes_without_preflight_or_paid_call(self):
        manager = self.manager()
        result = self.completed(manager, self.submit(manager, resume={}))
        self.assertEqual((result.model_calls, self.preflights), (0, []))

    def test_authenticated_api_can_submit_and_poll_the_revised_workflow(self):
        from fastapi.testclient import TestClient

        from app.api import deps
        from app.main import app
        from tests.test_skill_gap_authenticated_api import FakeAccounts, FakeVerifier

        manager = self.manager()
        accounts = FakeAccounts()
        accounts.user.target_role = "Data Analyst"
        other = uuid4()
        accounts.users[other] = SimpleNamespace(id=other, target_role="Data Analyst")
        verifier = FakeVerifier({"owner": USER_ID, "other": other})
        overrides = {deps.get_token_verifier: lambda: verifier, deps.get_account_service: lambda: accounts,
                     runs.get_skill_gap_run_manager: lambda: manager}
        headers = {"Authorization": "Bearer owner"}
        with patch.dict(app.dependency_overrides, overrides, clear=True), TestClient(app) as client:
            started = client.post("/skill-gaps/runs", json={}, headers=headers)
            self.assertEqual(started.status_code, 202, started.text)
            queued = runs.SkillGapRun.model_validate(started.json())
            view = self.completed(manager, queued)
            self.assertEqual((view.job_family, view.model_calls), ("data_analyst", 3))
            url = f"/skill-gaps/runs/{view.id}"
            self.assertEqual(client.get(url, headers=headers).json()["report"]["policy_version"],
                             runs.ENTRY_LEVEL_POLICY)
            self.assertEqual(client.get("/skill-gaps/runs/latest", headers=headers).json()["id"], view.id)
            self.assertEqual(client.get(url, headers={"Authorization": "Bearer other"}).status_code, 404)

    def test_api_factory_preserves_explicit_agent_configuration_by_default(self):
        configured = self.settings.model_copy(update={"skill_gap_foundation_agent_name": "existing-agent"})
        forced = configured.model_copy(update={"skill_gap_workflow": "entry_level"})
        legacy = self.settings.model_copy(update={"skill_gap_workflow": "legacy"})
        for settings, revised in ((self.settings, True), (configured, False), (forced, True), (legacy, False)):
            with self.subTest(settings=settings), patch.object(runs, "SkillGapSettings", return_value=settings), \
                    patch.object(entry_level_transport, "can_use_entry_level", return_value=True), \
                    patch.object(runs, "SkillGapRunManager") as constructor:
                try:
                    runs._cached_skill_gap_run_manager.__wrapped__()
                    constructor.assert_called_once()
                    self.assertEqual(constructor.call_args.kwargs["settings"], settings)
                    self.assertEqual(constructor.call_args.kwargs["entry_level_workflow"], revised)
                finally:
                    runs._cached_skill_gap_run_manager.cache_clear()
