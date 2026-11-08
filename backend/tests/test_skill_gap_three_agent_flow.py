"""Authenticated three-Agent report -> recommendations -> saved-plan regressions.

The application, run manager, evidence gates, scoring, catalogs, recommendation
filtering and plan store are real. Only identity/account persistence and model
transports are synthetic; neither Azure nor a database is contacted.
"""
from collections import Counter
from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tester:placeholder@localhost:5432/test")

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api import deps
from app.api.routes import resources as resource_routes
from app.main import app
from app.services.certifications.recommender import CertificationRecommender, get_certification_recommender
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.resources_agent import rank_projects
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from app.services.skill_gaps.schema import build_schema
from app.services.skill_gaps.skill_groups import GROUPS, build_group_format
from app.services.skill_gaps.skill_group_transport import PreparedGroup
from app.services.skill_gaps.transport import SkillGapConfigurationError
from tests.skill_gap_fixtures import (
    CONFIRMED_AT, RESUME_ID, USER_ID, absent_response, group_settings, reviewed_resume,
)
from tests.test_skill_gap_authenticated_api import FakeAccounts, FakeVerifier


class TrackedAccounts(FakeAccounts):
    def __init__(self):
        super().__init__()
        self.user.university = None
        self.reads_open = False
        self.read_ends = 0

    def get_resume(self, user, family):
        self.reads_open = True
        return super().get_resume(user, family)

    def end_reads(self):
        self.reads_open = False
        self.read_ends += 1


class ThreeAgentFullFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.accounts = TrackedAccounts()
        self.other = uuid4()
        self.accounts.users[self.other] = SimpleNamespace(
            id=self.other, target_role="Software Engineer", university=None)
        self.calls, self.project_calls, self.cert_calls = [], [], []
        self.preflights = 0
        self.preflight_error = None
        self.versions = {group: "1" for group in GROUPS}
        self.call_lock = Lock()
        self.fail_once = None
        self.attempts = Counter()
        self.release = Event()
        self.release.set()
        self.all_started = Event()
        self.barrier = None
        self.manager = self.new_manager()
        self.plan_store = LocalPlanStore(self.root / "plans")
        self.recommender = CertificationRecommender(self.root / "certs",
            configured=lambda: True, invoker=self.cert_agent)
        verifier = FakeVerifier({"owner-token": USER_ID, "other-token": self.other})
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        app.dependency_overrides[deps.get_account_service] = lambda: self.accounts
        app.dependency_overrides[get_skill_gap_run_manager] = lambda: self.manager
        app.dependency_overrides[get_certification_recommender] = lambda: self.recommender
        app.dependency_overrides[get_plan_store] = lambda: self.plan_store
        self.patches = [
            patch.object(resource_routes, "PROJECT_PICKS_DIR", self.root / "projects"),
            patch.object(resource_routes, "get_settings", return_value=SimpleNamespace(
                resources_project_endpoint="https://fixture.invalid")),
            patch.object(resource_routes, "recommend_projects", side_effect=self.project_agent),
            patch("psycopg.connect", side_effect=AssertionError("No real database in synthetic flow")),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer owner-token"}

    def tearDown(self):
        self.release.set()
        self.client.close()
        self.manager.close()
        app.dependency_overrides.clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def new_manager(self):
        settings = group_settings(**{f"skill_gap_{group}_agent_version": "latest" for group in GROUPS})
        return SkillGapRunManager(self.root / "runs", settings=settings,
                                  group_preflight=self.preflight, group_invoker=self.group_agent)

    def preflight(self, groups, save, *, settings):
        self.preflights += 1
        if self.preflight_error is not None:
            raise self.preflight_error
        prepared = {}
        for group in groups:
            version = self.versions[group]
            format_ = build_group_format(self.manager.catalog, group)
            definition = {"kind": "prompt", "model": "synthetic-model",
                "instructions": "Synthetic three-agent integration fixture.",
                "reasoning": {"effort": "medium"},
                "text": {"format": {"type": "json_schema", **format_}}}
            name = getattr(settings, f"skill_gap_{group}_agent_name")
            check = {"instructions_source": "foundry", "instructions_match": True,
                     "schema_match": True, "reasoning_match": True, "model_calls": 0}
            prepared[group] = PreparedGroup(group, settings.skill_gap_foundry_project_endpoint,
                                            name, version, definition, check)
            save(group, "configuration_check.json", check)
            save(group, "observed_agent.json", {"branch": group, "name": name,
                                               "version": version, "definition": definition})
        return prepared

    def group_agent(self, prepared, payload, save, on_request, timings):
        self.assertFalse(self.accounts.reads_open, "Agent must not hold a resume read transaction")
        on_request()
        group = prepared.branch
        with self.call_lock:
            self.calls.append((group, prepared.agent_version, deepcopy(payload)))
            self.attempts[group] += 1
            if len(self.calls) >= 3:
                self.all_started.set()
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        if not self.release.wait(timeout=5):
            raise RuntimeError("Synthetic Agent was not released")
        save("agent.raw.json", {"agent_reference": {"type": "agent_reference",
            "name": prepared.agent_name, "version": prepared.agent_version}, "model": "synthetic-model"})
        if group == self.fail_once and self.attempts[group] == 1:
            raise SkillGapConfigurationError("synthetic_group_failure", "The selected group could not finish.")
        output = absent_response(payload)
        family = payload["job_family"]
        uncertain = {"software_engineer": "system_design", "data_analyst": "requirements_analysis",
                     "ai_engineer": "machine_learning"}[family]
        if uncertain in output["result"]:
            output["result"][uncertain] = {"kind": "uncertain", "evidence_id": None,
                "reason": "The synthetic evidence leaves personal responsibility unresolved."}
        sql = "relational_sql" if family == "software_engineer" else "sql"
        sql_source = next((unit["id"] for source in payload["resume_sources"] for unit in source["units"]
                           if unit["kind"] == "listed" and unit["text"] == "SQL"), None)
        if sql in output["result"] and sql_source:
            output["result"][sql] = {"kind": "knowledge", "evidence_id": sql_source}
        return output

    def project_agent(self, **inputs):
        self.assertFalse(self.accounts.reads_open)
        self.project_calls.append(deepcopy(inputs))
        return rank_projects(**inputs)

    def cert_agent(self, payload):
        self.assertFalse(self.accounts.reads_open)
        self.cert_calls.append(deepcopy(payload))
        gaps = {row["skill_id"] for row in payload["gaps"]}
        result = []
        for certification in payload["catalog"]:
            covered = [skill for skill in certification["skill_ids"] if skill in gaps]
            if covered:
                result.append({"certification_id": certification["certification_id"],
                    "skill_ids": covered, "reason": "Covers an actual scored gap in this run."})
                break
        return {"recommendations": result}

    def start(self, family="software_engineer", **changes):
        response = self.client.post("/skill-gaps/runs", json={"job_family": family, **changes}, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def finished(self, started, expected="completed"):
        for _ in range(600):
            response = self.client.get("/skill-gaps/runs/" + started["id"], headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            run = response.json()
            if run["status"] in {"completed", "failed"}:
                self.assertEqual(run["status"], expected, run.get("error"))
                return run
            time.sleep(.01)
        self.fail("Synthetic full-flow run did not finish")

    def test_all_three_roles_complete_analysis_recommendations_and_saved_plan_flow(self):
        self.barrier = Barrier(3)
        for family, expected_count in [("software_engineer", 22), ("data_analyst", 18), ("ai_engineer", 23)]:
            with self.subTest(family=family):
                before = len(self.calls)
                run = self.finished(self.start(family))
                self.assertEqual((run["model_calls"], len(self.calls) - before), (3, 3))
                self.assertEqual(len(run["report"]["skills"]), expected_count)
                recent = self.calls[before:]
                self.assertEqual(len({row[0] for row in recent}), 3)
                self.assertTrue(all(row[2]["resume_sources"] == recent[0][2]["resume_sources"] for row in recent))
                assigned = [card["skill_id"] for _, _, p in recent for card in p["core_skills"]]
                self.assertEqual(len(assigned), len(set(assigned)))
                self.assertEqual(len(assigned), expected_count)
                evidence = {"task": "extract_resume_evidence", "result": {
                    "job_family": family, **{s["skill_id"]: s["agent_assessment"] for s in run["report"]["skills"]}}}
                Draft202012Validator(build_schema(self.manager.catalog)["schema"]).validate(evidence)
                restored = self.client.get("/skill-gaps/runs/latest", params={"job_family": family}, headers=self.headers)
                self.assertEqual((restored.status_code, restored.json()["id"]), (200, run["id"]))
                self.assertEqual(self.start(family)["id"], run["id"])
                self.assertEqual(len(self.calls), before + 3)
                projects = self.client.post("/resources/projects/from-skill-gap", json={"run_id": run["id"]}, headers=self.headers)
                self.assertEqual(projects.status_code, 200, projects.text)
                self.assertEqual(projects.json()["source"], "agent")
                inputs = self.project_calls[-1]
                unscored = set(run["report"]["unscored_skill_ids"])
                self.assertFalse(unscored & {s["skill_id"] for s in inputs["verified_skill_gaps"]})
                for recommendation in projects.json()["recommendations"]:
                    self.assertTrue(set(recommendation["addressed_skill_ids"]) <=
                                    {s["skill_id"] for s in inputs["verified_skill_gaps"]})
                project_count = len(self.project_calls)
                self.assertEqual(self.client.post("/resources/projects/from-skill-gap", json={"run_id": run["id"]},
                    headers=self.headers).status_code, 200)
                self.assertEqual(len(self.project_calls), project_count)
                certifications = self.client.post("/certifications/recommendations", json={"job_family": family}, headers=self.headers)
                self.assertEqual(certifications.status_code, 200, certifications.text)
                self.assertEqual(certifications.json()["skill_gap_run_id"], run["id"])
                self.assertEqual(certifications.json()["source"], "agent")
                self.assertFalse(unscored & {s["skill_id"] for s in self.cert_calls[-1]["gaps"]})
                cert_count = len(self.cert_calls)
                self.assertEqual(self.client.post("/certifications/recommendations", json={"job_family": family},
                    headers=self.headers).status_code, 200)
                self.assertEqual(len(self.cert_calls), cert_count)
                listed = self.client.get("/resources", params={"job_family": family}, headers=self.headers)
                self.assertEqual(listed.status_code, 200, listed.text)
                resource = next(r for r in listed.json()["resources"] if r["type"] == "project")
                saved = self.client.put("/plan/items/" + resource["id"], json={"job_family": family}, headers=self.headers)
                self.assertEqual(saved.status_code, 200, saved.text)
                done = self.client.put("/plan/items/" + resource["id"], json={"job_family": family, "status": "done"}, headers=self.headers)
                self.assertEqual(done.status_code, 200, done.text)
                self.assertEqual(done.json()["saved_at"], saved.json()["saved_at"])
                plan = self.client.get("/plan", params={"job_family": family}, headers=self.headers).json()
                self.assertEqual([(item["resource_id"], item["status"]) for item in plan["items"]], [(resource["id"], "done")])
                removed = self.client.delete("/plan/items/" + resource["id"], params={"job_family": family}, headers=self.headers)
                self.assertEqual(removed.status_code, 204, removed.text)
                self.assertEqual(self.client.get("/plan", params={"job_family": family}, headers=self.headers).json()["items"], [])
        self.assertGreater(self.accounts.read_ends, 0)

    def test_duplicates_do_not_multiply_requests_and_force_preserves_old_report_and_plan(self):
        self.release.clear()
        started = self.start()
        self.assertTrue(self.all_started.wait(timeout=3))
        self.assertEqual(self.start()["id"], started["id"])
        self.assertEqual(self.start(force=True)["id"], started["id"])
        self.release.set()
        first = self.finished(started)
        self.assertEqual(len(self.calls), 3)
        resource = self.client.get("/resources?job_family=software_engineer", headers=self.headers).json()["resources"][0]
        self.assertEqual(self.client.put("/plan/items/" + resource["id"], json={"job_family": "software_engineer"},
                                        headers=self.headers).status_code, 200)
        second = self.finished(self.start(force=True))
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual((second["model_calls"], len(self.calls)), (3, 6))
        self.assertEqual(self.client.get("/skill-gaps/runs/" + first["id"], headers=self.headers).json()["report"], first["report"])
        self.assertEqual(self.client.get("/plan?job_family=software_engineer", headers=self.headers).json()["items"][0]["resource_id"], resource["id"])

    def test_failed_group_is_not_a_partial_success_and_explicit_retry_reuses_valid_siblings(self):
        self.fail_once = "systems"
        failed = self.finished(self.start(), expected="failed")
        self.assertEqual((failed["model_calls"], failed["report"]), (3, None))
        project = self.client.post("/resources/projects/from-skill-gap", json={"run_id": failed["id"]}, headers=self.headers)
        self.assertEqual(project.status_code, 409, project.text)
        cert = self.client.post("/certifications/recommendations", json={"job_family": "software_engineer"}, headers=self.headers)
        self.assertEqual(cert.status_code, 409, cert.text)
        retried = self.finished(self.start(force=True))
        self.assertEqual(retried["model_calls"], 1)
        self.assertEqual(self.attempts, Counter(foundation=1, lifecycle=1, systems=2))

    def test_cloud_metadata_errors_are_503_and_historical_report_handoff_remains_readable(self):
        run = self.finished(self.start())
        calls = len(self.calls)
        self.preflight_error = SkillGapConfigurationError("group_unavailable", "The saved group cannot be checked.")
        latest = self.client.get("/skill-gaps/runs/latest?job_family=software_engineer", headers=self.headers)
        self.assertEqual(latest.status_code, 503, latest.text)
        cert = self.client.post("/certifications/recommendations", json={"job_family": "software_engineer"}, headers=self.headers)
        self.assertEqual(cert.status_code, 503, cert.text)
        new = self.client.post("/skill-gaps/runs", json={"job_family": "software_engineer", "force": True}, headers=self.headers)
        self.assertEqual(new.status_code, 503, new.text)
        historical = self.client.get("/skill-gaps/runs/" + run["id"], headers=self.headers)
        self.assertEqual(historical.status_code, 200, historical.text)
        project = self.client.post("/resources/projects/from-skill-gap", json={"run_id": run["id"]}, headers=self.headers)
        self.assertEqual(project.status_code, 200, project.text)
        self.assertEqual(len(self.calls), calls)

    def test_owner_and_current_resume_checks_are_preserved_across_consumers(self):
        run = self.finished(self.start())
        other_headers = {"Authorization": "Bearer other-token"}
        self.assertEqual(self.client.get("/skill-gaps/runs/" + run["id"], headers=other_headers).status_code, 404)
        self.assertEqual(self.client.post("/resources/projects/from-skill-gap", json={"run_id": run["id"]}, headers=other_headers).status_code, 404)
        other_resume = uuid4()
        self.accounts.links[(self.other, "software_engineer")] = other_resume
        self.accounts.resumes[other_resume] = SimpleNamespace(id=other_resume, user_id=self.other,
            original_filename="other.pdf", created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        self.assertEqual(self.client.post("/certifications/recommendations", json={"job_family": "software_engineer"}, headers=other_headers).status_code, 404)
        replacement = uuid4()
        self.accounts.links[(USER_ID, "software_engineer")] = replacement
        self.accounts.resumes[replacement] = SimpleNamespace(id=replacement, user_id=USER_ID,
            original_filename="replacement.pdf", created_at=CONFIRMED_AT, confirmed_data=reviewed_resume())
        self.assertEqual(self.client.post("/resources/projects/from-skill-gap", json={"run_id": run["id"]}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post("/certifications/recommendations", json={"job_family": "software_engineer"}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get("/skill-gaps/runs/" + run["id"], headers=self.headers).status_code, 200)


if __name__ == "__main__":
    unittest.main()
