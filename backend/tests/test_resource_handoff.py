import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

from fastapi import HTTPException
from app.api.routes.resources import inputs_from_report, projects_from_skill_gap, RunProjectRequest


class HandoffTest(unittest.TestCase):
    def test_ranked_scored_gaps_only_and_family_mapping(self):
        report = {"job_family": "data_analyst", "priority_order": ["sql", "unknown", "uncertain"], "skills": [
            {"skill_id": "sql", "skill_name": "SQL", "skill_gap": 0.5, "calculation_state": "scored"},
            {"skill_id": "uncertain", "skill_name": "Python", "skill_gap": None, "calculation_state": "needs_confirmation"},
        ]}
        self.assertEqual(inputs_from_report(report, "data_analyst"), {"career_path": "Data Science", "existing_skills": [], "skill_gaps": ["SQL"]})

    def test_owner_resume_and_completed_state(self):
        uid, rid = uuid4(), uuid4()
        saved = SimpleNamespace(user_id=uid, resume_id=rid)
        run = SimpleNamespace(resume_id=rid, status="completed", job_family="software_engineer", report={"job_family": "software_engineer", "priority_order": ["web"], "skills": [{"skill_id": "web", "skill_name": "Web development", "skill_gap": 0.5, "calculation_state": "scored"}]})
        class Manager:
            def get(self, identifier, *, user_id):
                if user_id != uid:
                    raise KeyError(identifier)
                return run
        with patch("app.api.routes.resources.recommend_projects", return_value={"recommendations": []}) as recommend:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), saved, Manager())
            self.assertEqual(recommend.call_args.kwargs["skill_gaps"], ["Web development"])
        with self.assertRaises(HTTPException) as error:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), SimpleNamespace(user_id=uuid4(), resume_id=rid), Manager())
        self.assertEqual(error.exception.status_code, 404)
        run.resume_id = uuid4()
        with self.assertRaises(HTTPException) as error:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), saved, Manager())
        self.assertEqual(error.exception.status_code, 409)
        run.resume_id, run.status = rid, "running"
        with self.assertRaises(HTTPException) as error:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), saved, Manager())
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
