"""Resource catalog filtering, the saved plan API and the overall match summary. No DB or network."""
from pathlib import Path
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient

from app.api import deps
from app.core.security import SupabaseTokenVerifier
from app.main import app
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.resources import family_skills, load_catalog, resources_for
from app.services.skill_gaps.match import summarize_match
from tests.support import SUPABASE_URL, FakeJwks, make_token, new_signing_key
from tests.test_me import FakeAccountService, onboarding_body


class ResourceCatalogTests(unittest.TestCase):
    def test_every_catalog_skill_has_a_resource_for_every_school(self) -> None:
        for family in ("software_engineer", "data_analyst", "ai_engineer"):
            for school in ("University of Wisconsin–Madison", "Another University"):
                covered = {skill for entry in resources_for(family, school) for skill in entry["skills"]}
                self.assertEqual(set(), family_skills(family) - covered, (family, school))

    def test_resources_close_only_the_roles_skills(self) -> None:
        skills = family_skills("data_analyst")
        for entry in resources_for("data_analyst", None):
            self.assertTrue(entry["skills"])
            self.assertTrue(set(entry["skills"]) <= skills, entry["id"])

    def test_school_resources_need_a_matching_school(self) -> None:
        def ids(school):
            return {entry["id"] for entry in resources_for("data_analyst", school)}
        self.assertIn("uw-cs-564", ids("University of Wisconsin-Madison"))
        self.assertIn("uw-cs-564", ids("UW–Madison"))
        self.assertNotIn("uw-cs-564", ids("Purdue University"))
        self.assertNotIn("uw-cs-564", ids(None))

    def test_certifications_come_from_the_certification_catalog(self) -> None:
        self.assertFalse([entry["id"] for entry in load_catalog() if entry["type"] == "certification"])
        practitioner = {entry["id"]: entry for entry in resources_for("software_engineer", None)}["aws-cloud-practitioner"]
        self.assertEqual("certification", practitioner["type"])
        self.assertEqual(["cloud"], practitioner["skills"])
        self.assertNotIn("aws-cloud-practitioner", {entry["id"] for entry in resources_for("data_analyst", None)})
        for family in ("software_engineer", "data_analyst", "ai_engineer"):
            family_ids = [entry["id"] for entry in resources_for(family, None)]
            self.assertEqual(len(family_ids), len(set(family_ids)), family)

    def test_catalog_skill_ids_exist(self) -> None:
        known = family_skills("software_engineer") | family_skills("data_analyst") | family_skills("ai_engineer")
        for entry in load_catalog():
            self.assertTrue(set(entry["skills"]) <= known, entry["id"])


def _skill(strength, required, preferred=0, n=100):
    return {"resume_evidence_strength": strength,
            "demand": {"N": n, "required_job_count": required, "preferred_only_job_count": preferred}}


class MatchSummaryTests(unittest.TestCase):
    def test_weights_evidence_by_demand_and_skips_unscored_skills(self) -> None:
        report = {"skills": [_skill(1.0, 60), _skill(0.0, 20), _skill(None, 90), _skill(0.5, 0)]}
        match = summarize_match(report)
        self.assertEqual(0.75, match["score"])
        self.assertEqual(2, match["scored_skill_count"])
        self.assertEqual(1, match["unscored_skill_count"])

    def test_no_report_or_no_demand_has_no_match(self) -> None:
        self.assertIsNone(summarize_match(None))
        self.assertIsNone(summarize_match({"skills": [_skill(None, 10), _skill(1.0, 0)]}))


class PlanApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = LocalPlanStore(Path(self.temp.name))
        key = new_signing_key()
        verifier = SupabaseTokenVerifier(SUPABASE_URL, jwks_client=FakeJwks(key))
        self.accounts = FakeAccountService()
        app.dependency_overrides[deps.get_account_service] = lambda: self.accounts
        app.dependency_overrides[deps.get_token_verifier] = lambda: verifier
        app.dependency_overrides[get_plan_store] = lambda: self.store
        self.client = TestClient(app)
        self.user_id = uuid.uuid4()
        self.headers = {"Authorization": f"Bearer {make_token(key, sub=str(self.user_id), email='ada@example.com')}"}
        self.client.post("/me", json=onboarding_body(), headers=self.headers)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.temp.cleanup()

    def plan(self, family="data_analyst"):
        return self.client.get(f"/plan?job_family={family}", headers=self.headers).json()["items"]

    def test_resources_need_onboarding(self) -> None:
        self.assertEqual(401, self.client.get("/resources?job_family=data_analyst").status_code)
        self.accounts.users.clear()
        self.assertEqual(403, self.client.get("/resources?job_family=data_analyst", headers=self.headers).status_code)

    def test_resources_follow_the_accounts_school(self) -> None:
        listed = self.client.get("/resources?job_family=data_analyst", headers=self.headers).json()
        self.assertIn("uw-cs-564", [entry["id"] for entry in listed["resources"]])

    def test_save_mark_done_and_remove(self) -> None:
        saved = self.client.put("/plan/items/mode-sql-tutorial", json={"job_family": "data_analyst"}, headers=self.headers)
        self.assertEqual(200, saved.status_code, saved.text)
        self.assertEqual([("mode-sql-tutorial", "saved")], [(i["resource_id"], i["status"]) for i in self.plan()])
        self.assertEqual([], self.plan("software_engineer"))

        done = self.client.put("/plan/items/mode-sql-tutorial", json={"job_family": "data_analyst", "status": "done"},
                               headers=self.headers).json()
        self.assertEqual("done", done["status"])
        self.assertIsNotNone(done["done_at"])
        self.assertEqual(saved.json()["saved_at"], done["saved_at"])

        removed = self.client.delete("/plan/items/mode-sql-tutorial?job_family=data_analyst", headers=self.headers)
        self.assertEqual(204, removed.status_code)
        self.assertEqual([], self.plan())

    def test_rejects_unknown_or_other_role_resources(self) -> None:
        for resource_id in ("not-a-resource", "neetcode-150"):
            response = self.client.put(f"/plan/items/{resource_id}", json={"job_family": "data_analyst"},
                                       headers=self.headers)
            self.assertEqual(404, response.status_code, resource_id)
        self.assertEqual(422, self.client.put("/plan/items/sqlbolt", json={"job_family": "data_analyst",
                                              "status": "archived"}, headers=self.headers).status_code)

    def test_plans_are_per_student(self) -> None:
        self.client.put("/plan/items/sqlbolt", json={"job_family": "data_analyst"}, headers=self.headers)
        self.assertEqual([], self.store.items(uuid.uuid4(), "data_analyst"))


if __name__ == "__main__":
    unittest.main()
