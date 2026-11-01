"""The résumé child backfill loop, with a fake session (no database)."""
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# CI has no .env; creating the engine doesn't connect, so a dummy URL is enough.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:not-a-real-password@localhost:5432/test")

from sqlalchemy.exc import IntegrityError

from scripts import backfill_resume_children as script
from tests.test_resume_children import project, resume_with


class BackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resumes = [
            resume_with(technical_skills=["Python", "SQL"]),
            resume_with(projects=[project("A", ["Go"])]),
            resume_with(technical_skills=["Rust"]),
        ]
        by_id = {resume.id: resume for resume in self.resumes}
        self.session = mock.Mock()
        self.session.scalars.return_value = [resume.id for resume in self.resumes]
        self.session.get.side_effect = lambda model, resume_id: by_id[resume_id]

    def test_commits_each_resume_and_counts_its_rows(self) -> None:
        results = script.backfill(self.session, dry_run=False)

        self.assertEqual([r.id for r in self.resumes], [r.resume_id for r in results])
        self.assertEqual({"resume_skills": 2}, dict(results[0].counts))
        self.assertEqual({"resume_projects": 1, "resume_skills": 1}, dict(results[1].counts))
        self.assertEqual(3, self.session.commit.call_count)
        self.session.rollback.assert_not_called()

    def test_dry_run_flushes_then_rolls_back(self) -> None:
        results = script.backfill(self.session, dry_run=True)

        self.assertTrue(all(r.error is None for r in results))
        self.assertEqual(3, self.session.flush.call_count)  # the database still checks the rows
        self.assertEqual(3, self.session.rollback.call_count)
        self.session.commit.assert_not_called()

    def test_a_failed_resume_is_rolled_back_and_the_rest_continue(self) -> None:
        diag = mock.Mock(constraint_name="uq_resume_skills_evidence")
        error = IntegrityError("INSERT ... ('secret résumé value')", {}, mock.Mock(diag=diag))
        self.session.flush.side_effect = [None, error, None]

        results = script.backfill(self.session, dry_run=False)

        self.assertEqual([None, "IntegrityError (uq_resume_skills_evidence)", None], [r.error for r in results])
        self.assertNotIn("secret", results[1].error)
        self.assertEqual(2, self.session.commit.call_count)
        self.assertEqual(1, self.session.rollback.call_count)

    def test_exit_status_is_1_when_any_resume_failed(self) -> None:
        failed = [script.ResumeResult(uuid.uuid4()), script.ResumeResult(uuid.uuid4(), error="ValidationError")]
        with mock.patch.object(script, "SessionLocal"), \
             mock.patch.object(script, "backfill", return_value=failed), \
             mock.patch.object(sys, "argv", ["backfill"]), \
             mock.patch("builtins.print"):
            self.assertEqual(1, script.main())
        with mock.patch.object(script, "SessionLocal"), \
             mock.patch.object(script, "backfill", return_value=failed[:1]), \
             mock.patch.object(sys, "argv", ["backfill", "--dry-run"]), \
             mock.patch("builtins.print"):
            self.assertEqual(0, script.main())


if __name__ == "__main__":
    unittest.main()
