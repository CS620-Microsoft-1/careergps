"""Synthetic, offline data-source checks; no real user rows or report artifacts."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.copilot.readonly import ResumeSnapshot, canonical_hash
from app.services.copilot import reports
from app.services.copilot.reports import ReadOnlyReportSource
from app.services.skill_gaps.schema import SCHEMA_NAME
import tests.test_copilot_readonly as fixtures
from tests.skill_gap_fixtures import group_manager, reviewed_resume


class ResumeSnapshotTests(unittest.TestCase):
    def setUp(self):
        # Reuse only the synthetic SQLite fixture, not its inherited test methods.
        self.fixture = fixtures.ReadOnlyResumeSourceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.source

    def test_account_lookup_is_private_read_only_and_missing_account_is_403(self):
        self.assertIsNone(self.source.require_account(fixtures.USER))
        with self.assertRaises(HTTPException) as caught:
            self.source.require_account(fixtures.MISSING)
        self.assertEqual(caught.exception.status_code, 403)
        self.fixture.assert_released_without_commit()

    def test_snapshot_preserves_all_confirmed_data_and_uses_the_run_canonical_hash(self):
        snapshot = self.source.get_snapshot(fixtures.USER, "ai_engineer")
        self.assertEqual(snapshot.id, fixtures.RESUME)
        self.assertEqual(snapshot.user_id, fixtures.USER)
        self.assertEqual(snapshot.confirmed_data, self.fixture.saved)
        expected = canonical_hash(self.fixture.saved)
        self.assertEqual(snapshot.resume_hash, expected)
        snapshot.confirmed_data["technical_skills"].append("Changed only in this detached copy")
        self.assertEqual(self.source.get_snapshot(fixtures.USER, "ai_engineer").resume_hash, expected)
        self.fixture.assert_released_without_commit()


class SavedReportTests(unittest.TestCase):
    def setUp(self):
        network = patch("socket.socket.connect", side_effect=AssertionError("Offline test attempted network access"))
        network.start()
        self.addCleanup(network.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "existing"
        self.directory.mkdir()
        data = reviewed_resume()
        self.snapshot = ResumeSnapshot(id=fixtures.RESUME, user_id=fixtures.USER, job_family="ai_engineer",
            filename="synthetic.pdf", confirmed_at=datetime(2026, 11, 17, 12, tzinfo=timezone.utc),
            confirmed_data=data, resume_hash=canonical_hash(data))
        self.source = ReadOnlyReportSource(self.directory)

    def make_run(self, *, owner=None, resume_id=None, family=None, resume_hash=None,
                 status="completed", created="2026-11-17T13:00:00+00:00"):
        identifier = uuid4().hex
        folder = self.directory / identifier
        folder.mkdir()
        state = {"id": identifier, "user_id": str(owner or self.snapshot.user_id),
                 "resume_id": str(resume_id or self.snapshot.id), "job_family": family or self.snapshot.job_family,
                 "resume_hash": resume_hash or self.snapshot.resume_hash, "calculation_fingerprint": "saved-version-a",
                 "created_at": created, "completed_at": "2026-11-17T15:00:00+00:00" if status == "completed" else None,
                 "status": status}
        self.write_state(folder, state)
        reviewed = {"confirmed": True, "resume_source": "resumes.confirmed_data", "user_id": state["user_id"],
                    "resume_id": state["resume_id"], "job_family": state["job_family"],
                    "resume_hash": state["resume_hash"], "reviewed_resume": deepcopy(self.snapshot.confirmed_data)}
        report = {"user_id": state["user_id"], "resume_id": state["resume_id"], "job_family": state["job_family"],
                  "database_used": True, "policy_version": "saved-rubric", "calibration_status": "uncalibrated",
                  "metric": "resume evidence gap", "priority_order": ["sql"], "unscored_skill_ids": ["pending"],
                  "limitations": ["Missing evidence does not establish inability."], "semantic_evidence_verified": False,
                  "source_index": {"e001": {"id": "e001", "text": "SQL", "path": "technical_skills[1]"}},
                  "skills": [
                      {"skill_id": "sql", "skill_name": "SQL", "calculation_state": "scored",
                       "resume_evidence_strength": .25, "skill_gap": .75, "skill_gap_grade": "D", "priority": .3,
                       "agent_assessment": {"kind": "knowledge", "evidence_id": "e001"},
                       "scoring_breakdown": {"score": .25, "reason": "selected_explicit_knowledge"}},
                      {"skill_id": "pending", "skill_name": "Pending skill", "calculation_state": "needs_confirmation",
                       "resume_evidence_strength": None, "skill_gap": None, "skill_gap_grade": None, "priority": None,
                       "agent_assessment": {"kind": "uncertain", "reason": "Original evidence requires review"}},
                  ]}
        (folder / "reviewed_resume.json").write_text(json.dumps(reviewed))
        (folder / "skill_gaps.json").write_text(json.dumps(report))
        return folder, state, report

    def write_state(self, folder, state):
        state["cache_key"] = canonical_hash({"user_id": state["user_id"], "resume_id": state["resume_id"],
            "resume_hash": state["resume_hash"], "job_family": state["job_family"], "contract": SCHEMA_NAME,
            "fingerprint": state["calculation_fingerprint"]})
        (folder / "status.json").write_text(json.dumps(state))

    def bytes_before(self):
        return {str(path.relative_to(self.directory)): path.read_bytes() for path in self.directory.rglob("*") if path.is_file()}

    def test_existing_scores_uncertainty_and_sources_are_returned_without_writes_or_recalculation(self):
        folder, state, original = self.make_run()
        before = self.bytes_before()
        result = self.source.get_report(self.snapshot)
        self.assertEqual(result["run_id"], state["id"])
        self.assertEqual(result["report"]["skills"], original["skills"])
        self.assertEqual(result["report"]["source_index"], original["source_index"])
        self.assertEqual(result["report"]["limitations"], original["limitations"])
        self.assertIn("not revalidated", result["freshness"])
        self.assertNotIn("user_id", json.dumps(result))
        self.assertNotIn("reviewed_resume", result)
        self.assertEqual(self.bytes_before(), before)

    def test_actual_saved_run_format_with_synthetic_agent_outputs_is_compatible(self):
        manager = group_manager(self.directory)
        self.addCleanup(manager.close)
        run = manager.submit(user_id=self.snapshot.user_id, resume_id=self.snapshot.id,
            reviewed_resume=self.snapshot.confirmed_data, filename=self.snapshot.filename,
            confirmed_at=self.snapshot.confirmed_at, job_family=self.snapshot.job_family)
        for _ in range(200):
            run = manager.get(run.id, user_id=self.snapshot.user_id)
            if run.status in ("completed", "failed"):
                break
            time.sleep(.01)
        self.assertEqual(run.status, "completed")
        before = self.bytes_before()
        result = self.source.get_report(self.snapshot)
        self.assertEqual(result["run_id"], run.id)
        for original, selected in zip(run.report["skills"], result["report"]["skills"]):
            for key in ("resume_evidence_strength", "skill_gap", "priority", "calculation_state"):
                self.assertEqual(selected[key], original[key])
        self.assertEqual(self.bytes_before(), before)

    def test_foreign_owner_direction_or_resume_are_not_adopted_as_current(self):
        foreign, _, _ = self.make_run(owner=fixtures.OTHER)
        self.make_run(family="software_engineer")
        # These accounts' result files need not even be readable by the adapter.
        (foreign / "skill_gaps.json").write_text("private foreign invalid report")
        with self.assertRaises(HTTPException) as caught:
            self.source.get_report(self.snapshot)
        self.assertEqual(caught.exception.status_code, 404)
        self.make_run(resume_id=fixtures.SECOND)
        with self.assertRaises(HTTPException) as caught:
            self.source.get_report(self.snapshot)
        self.assertEqual(caught.exception.status_code, 409)

    def test_changed_current_content_rejects_previous_report(self):
        self.make_run()
        changed = deepcopy(self.snapshot.confirmed_data)
        changed["technical_skills"].append("New confirmed skill")
        with self.assertRaises(HTTPException) as caught:
            self.source.get_report(replace(self.snapshot, confirmed_data=changed, resume_hash=canonical_hash(changed)))
        self.assertEqual(caught.exception.status_code, 409)

    def test_newer_matching_incomplete_or_failed_run_never_falls_back_or_recovers_files(self):
        self.make_run(created="2026-11-17T12:00:00+00:00")
        folder, state, _ = self.make_run(created="2026-11-17T13:00:00+00:00", status="queued")
        for status in ("queued", "running", "failed"):
            state["status"] = status
            self.write_state(folder, state)
            before = self.bytes_before()
            with self.subTest(status=status), self.assertRaises(HTTPException) as caught:
                self.source.get_report(self.snapshot)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertEqual(self.bytes_before(), before)

    def test_latest_matching_completed_run_is_selected(self):
        self.make_run(created="2026-11-17T12:00:00+00:00")
        _, state, _ = self.make_run(created="2026-11-17T13:00:00+00:00")
        self.assertEqual(self.source.get_report(self.snapshot)["run_id"], state["id"])

    def test_explicit_page_report_selects_that_checked_run_instead_of_newer_other_version(self):
        _, selected, _ = self.make_run(created="2026-11-17T12:00:00+00:00")
        newer_folder, newer, _ = self.make_run(created="2026-11-17T13:00:00+00:00")
        newer["calculation_fingerprint"] = "different-historical-version"
        self.write_state(newer_folder, newer)
        self.assertEqual(self.source.get_report(self.snapshot)["run_id"], newer["id"])
        result = self.source.get_report(self.snapshot, report_id=selected["id"])
        self.assertEqual(result["run_id"], selected["id"])
        self.assertEqual(result["calculation_fingerprint"], selected["calculation_fingerprint"])

    def test_explicit_foreign_wrong_direction_or_missing_selector_never_falls_back(self):
        self.make_run()
        _, foreign, _ = self.make_run(owner=fixtures.OTHER)
        _, direction, _ = self.make_run(family="software_engineer")
        for identifier in (foreign["id"], direction["id"], uuid4().hex):
            with self.subTest(identifier=identifier), self.assertRaises(HTTPException) as caught:
                self.source.get_report(self.snapshot, report_id=identifier)
            self.assertEqual(caught.exception.status_code, 404)

    def test_explicit_stale_hash_or_resume_and_unfinished_selector_never_fall_back(self):
        self.make_run()
        _, stale_id, _ = self.make_run(resume_id=fixtures.SECOND)
        _, stale_hash, _ = self.make_run(resume_hash="f" * 64)
        _, failed, _ = self.make_run(status="failed")
        for identifier in (stale_id["id"], stale_hash["id"], failed["id"]):
            with self.subTest(identifier=identifier), self.assertRaises(HTTPException) as caught:
                self.source.get_report(self.snapshot, report_id=identifier)
            self.assertEqual(caught.exception.status_code, 409)

    def test_report_selector_cannot_select_a_path_or_malformed_identifier(self):
        self.make_run()
        for identifier in ("../private", "/tmp/private", "a" * 31, "A" * 32, 123, ""):
            with self.subTest(identifier=identifier), self.assertRaises(HTTPException) as caught:
                self.source.get_report(self.snapshot, report_id=identifier)
            self.assertEqual(caught.exception.status_code, 422)

    def test_corrupt_metadata_mismatched_input_or_report_owner_are_sanitized(self):
        folder, state, report = self.make_run()
        for artifact, update in (("status.json", {**state, "cache_key": "private-bad-key"}),
                                 ("reviewed_resume.json", {"private-invalid": "private-data"}),
                                 ("skill_gaps.json", {**report, "user_id": str(fixtures.OTHER)})):
            path = folder / artifact
            before = path.read_bytes()
            path.write_text(json.dumps(update))
            with self.subTest(artifact=artifact), self.assertRaises(HTTPException) as caught:
                self.source.get_report(self.snapshot)
            self.assertEqual(caught.exception.status_code, 503)
            self.assertNotIn("private-", str(caught.exception.detail))
            path.write_bytes(before)

    def test_symlinks_missing_artifacts_and_oversized_result_fail_closed(self):
        folder, _, report = self.make_run()
        path = folder / "skill_gaps.json"
        path.unlink()
        with self.assertRaises(HTTPException) as caught:
            self.source.get_report(self.snapshot)
        self.assertEqual(caught.exception.status_code, 503)
        outside = Path(self.temp.name) / "private.json"
        outside.write_text(json.dumps(report))
        path.symlink_to(outside)
        with self.assertRaises(HTTPException) as caught:
            self.source.get_report(self.snapshot)
        self.assertEqual(caught.exception.status_code, 503)
        path.unlink()
        path.write_text(json.dumps(report))
        with patch.object(reports, "MAX_REPORT_CHARACTERS", 100):
            with self.assertRaises(HTTPException) as caught:
                self.source.get_report(self.snapshot)
            self.assertEqual(caught.exception.status_code, 503)

    def test_absent_directory_is_not_created(self):
        missing = Path(self.temp.name) / "not-created"
        with self.assertRaises(HTTPException) as caught:
            ReadOnlyReportSource(missing).get_report(self.snapshot)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
