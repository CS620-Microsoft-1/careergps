import tempfile
import unittest
import os
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

from fastapi import HTTPException
from app.api.routes import resources as routes
from app.api.routes.resources import inputs_from_report, projects_from_skill_gap, RunProjectRequest
from app.services.resources_agent import rank_projects


class HandoffTest(unittest.TestCase):
    def test_ranked_scored_gaps_only_and_family_mapping(self):
        report = {"job_family": "data_analyst", "priority_order": ["sql", "unknown", "uncertain"], "skills": [
            {"skill_id": "sql", "skill_name": "SQL", "skill_gap": 0.5, "calculation_state": "scored"},
            {"skill_id": "uncertain", "skill_name": "Python", "skill_gap": None, "calculation_state": "needs_confirmation"},
        ]}
        inputs = inputs_from_report(report, "data_analyst")
        self.assertEqual(inputs["career_path"], "Data Analyst")
        self.assertEqual(inputs["skill_gaps"], ["SQL"])
        self.assertEqual(inputs["verified_skill_gaps"][0]["skill_id"], "sql")
        catalog = json.loads((Path(__file__).resolve().parents[1] / "data" / "projects.json").read_text())
        matched = [p for p in catalog if p["career_path"] == inputs["career_path"]]
        self.assertEqual(len(matched), 3)
        self.assertIn("Sales Performance Dashboard", [p["title"] for p in matched])

    def test_owner_resume_and_completed_state(self):
        uid, rid = uuid4(), uuid4()
        user = SimpleNamespace(id=uid)
        # The role's destination uses résumé rid.
        accounts = SimpleNamespace(get_resume=lambda owner, family: SimpleNamespace(id=rid))
        run = SimpleNamespace(id=uuid4().hex, resume_id=rid, status="completed", job_family="software_engineer", report={"job_family": "software_engineer", "priority_order": ["frontend"], "skills": [{"skill_id": "frontend", "skill_name": "Frontend development", "skill_gap": 0.5, "calculation_state": "scored"}]})
        class Manager:
            def get(self, identifier, *, user_id):
                if user_id != uid:
                    raise KeyError(identifier)
                return run
        configured = SimpleNamespace(resources_project_endpoint="https://example.test")
        with patch("app.api.routes.resources.get_settings", return_value=configured), \
             patch("app.api.routes.resources.recommend_projects", return_value={"recommendations": []}) as recommend:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), user, accounts, Manager())
            self.assertEqual(recommend.call_args.kwargs["skill_gaps"], ["Frontend development"])
        with self.assertRaises(HTTPException) as error:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), SimpleNamespace(id=uuid4()), accounts, Manager())
        self.assertEqual(error.exception.status_code, 404)
        run.resume_id = uuid4()
        with self.assertRaises(HTTPException) as error:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), user, accounts, Manager())
        self.assertEqual(error.exception.status_code, 409)
        run.resume_id, run.status = rid, "running"
        with self.assertRaises(HTTPException) as error:
            projects_from_skill_gap(RunProjectRequest(run_id="one"), user, accounts, Manager())
        self.assertEqual(error.exception.status_code, 409)


    def test_rules_cover_the_highest_priority_gaps_first(self):
        gaps = [{"skill_id": "rag", "skill_name": "RAG", "definition": ""},
                {"skill_id": "mlops", "skill_name": "MLOps", "definition": ""}]
        result = rank_projects("AI/ML Engineering", [], ["RAG", "MLOps"], verified_skill_gaps=gaps)
        self.assertEqual(["aiml_02", "aiml_03"], [item["project_id"] for item in result["recommendations"]])
        self.assertEqual(["rag"], result["recommendations"][0]["addressed_skill_ids"])
        self.assertIsNone(result["no_match_reason"])
        none = rank_projects("AI/ML Engineering", [], ["RAG"], available_hours=5, verified_skill_gaps=gaps)
        self.assertEqual([], none["recommendations"])
        self.assertTrue(none["no_match_reason"])


class ProjectPicksTest(unittest.TestCase):
    """The rule ranking without the agent; agent picks are cached per run."""

    def setUp(self):
        self.rid, self.uid = uuid4(), uuid4()
        self.user = SimpleNamespace(id=self.uid)
        self.accounts = SimpleNamespace(get_resume=lambda owner, family: SimpleNamespace(id=self.rid))
        run = SimpleNamespace(id=uuid4().hex, resume_id=self.rid, status="completed", job_family="ai_engineer", report={
            "job_family": "ai_engineer", "priority_order": ["rag"],
            "skills": [{"skill_id": "rag", "skill_name": "Retrieval-augmented generation", "skill_gap": 0.5, "calculation_state": "scored"}]})
        self.manager = SimpleNamespace(get=lambda identifier, user_id: run)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(routes, "PROJECT_PICKS_DIR", Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self):
        return projects_from_skill_gap(RunProjectRequest(run_id="one"), self.user, self.accounts, self.manager)

    def test_without_the_agent_uses_rules(self):
        with patch.object(routes, "get_settings", return_value=SimpleNamespace(resources_project_endpoint=None)), \
             patch.object(routes, "recommend_projects") as agent:
            result = self.call()
        agent.assert_not_called()
        self.assertEqual("rules", result["source"])
        self.assertEqual(["aiml_02"], [item["project_id"] for item in result["recommendations"]])

    def test_agent_failure_falls_back_and_success_is_cached(self):
        configured = SimpleNamespace(resources_project_endpoint="https://example.test")
        with patch.object(routes, "get_settings", return_value=configured):
            with patch.object(routes, "recommend_projects", side_effect=RuntimeError("down")):
                self.assertEqual("rules", self.call()["source"])
            picks = {"recommendations": [], "no_match_reason": "None fit."}
            with patch.object(routes, "recommend_projects", return_value=picks) as agent:
                self.assertEqual("agent", self.call()["source"])
                self.assertEqual("agent", self.call()["source"])
            agent.assert_called_once()

    def test_concurrent_requests_for_one_run_share_one_agent_call(self):
        calls = []
        def slow_agent(**inputs):
            calls.append(inputs)
            time.sleep(0.2)
            return {"recommendations": [], "no_match_reason": "None fit."}
        configured = SimpleNamespace(resources_project_endpoint="https://example.test")
        results = []
        with patch.object(routes, "get_settings", return_value=configured), \
             patch.object(routes, "recommend_projects", side_effect=slow_agent):
            threads = [threading.Thread(target=lambda: results.append(self.call())) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(1, len(calls))
        self.assertEqual(["agent", "agent"], [result["source"] for result in results])


if __name__ == "__main__":
    unittest.main()
