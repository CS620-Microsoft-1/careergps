"""Exercise recovered evidence through the production selector and scorer."""

from copy import deepcopy
import json
import unittest

from app.services.skill_gaps import entry_level
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.entry_level import _selection
from app.services.skill_gaps.input import prepare
from app.services.skill_gaps.skill_groups import GROUP_SKILLS


FAMILIES = ("ai_engineer", "data_analyst")
FLOW = "I moved records from the vendor endpoint into the reporting store nightly"
METHOD = "from the vendor endpoint into the reporting store nightly"
CHECK = "verified row counts matched"
COMPLETE = f"{FLOW} and {CHECK}."


class EntryLevelSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8-sig"))

    def base(self, family, *projects):
        return prepare(family, {"projects": [
            {"name": f"Archive {index}", "content": list(bullets)}
            for index, bullets in enumerate(projects)
        ]}, "selection-regression", self.catalog)

    def payload(self, base):
        groups, diagnostics = entry_level.prepare_group_inputs(base)
        group = next(group for group, skills in GROUP_SKILLS[base["job_family"]].items()
                     if "data_pipelines" in skills)
        return groups[group], diagnostics

    def assessment(self, payload, diagnostics, proofs):
        """Supply a controlled Agent response, retaining production validation."""
        output = entry_level.absent_group_output(payload)
        for criterion in output["result"]["data_pipelines"]["criteria"]:
            cid = criterion["criterion_id"]
            if cid not in proofs:
                continue
            uid, quote = proofs[cid]
            pid = f"p{len(output['proofs']) + 1}"
            criterion.update(status="supported", basis="practice", proof_ids=[pid])
            output["proofs"].append({"proof_id": pid, "unit_id": uid, "quote": quote})
        report, _ = entry_level.assess(payload["evidence_scope"]["branch"], output, payload, diagnostics)
        return next(row for row in report["skills"] if row["skill_id"] == "data_pipelines")

    def permissions(self, payload):
        return payload["fixed_evidence_packets"]["skills"]["data_pipelines"]["criterion_unit_ids"]

    def assert_consistent_diagnostics(self, base, payload, diagnostics):
        detail = diagnostics["skills"]["data_pipelines"]
        activities = detail["criterion_unit_ids_by_activity"]
        chosen = [source for source in base["resume_sources"] if source["id"] in activities]
        self.assertEqual(detail["selected_activity_ids"], [source["id"] for source in chosen])
        self.assertEqual(detail["eligible_unit_ids"], [unit["id"] for source in chosen
                         for unit in source["units"] if unit["kind"] == "claim"])
        packet = payload["fixed_evidence_packets"]["skills"]["data_pipelines"]
        self.assertEqual(packet["unit_ids"], [unit["id"] for source in chosen for unit in source["units"]])
        for cid, ids in packet["criterion_unit_ids"].items():
            self.assertEqual(ids, [uid for source in chosen for uid in activities[source["id"]][cid]])
            self.assertEqual(len(ids), len(set(ids)))
        entry_level.validate_payload(payload["evidence_scope"]["branch"], payload)

    def test_newly_recovered_complete_flow_scores_100_in_both_families(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                base = self.base(family, [COMPLETE])
                original = deepcopy(base)
                _, before = _selection._select_criteria(base)
                self.assertEqual(before["skills"]["data_pipelines"]["selected_activity_ids"], [])
                payload, diagnostics = self.payload(base)
                self.assertEqual(self.permissions(payload), {"c1": ["e001"], "c2": ["e001"], "c3": ["e001"]})
                row = self.assessment(payload, diagnostics, {
                    "c1": ("e001", COMPLETE), "c2": ("e001", METHOD), "c3": ("e001", CHECK),
                })
                self.assertEqual((row["entry_level_score"], row["errors"]), (1.0, []))
                self.assertEqual(row["calculation_state"], "scored")
                self.assertFalse(diagnostics["skills"]["data_pipelines"]["search_incomplete"])
                self.assert_consistent_diagnostics(base, payload, diagnostics)
                self.assertEqual(base, original)

    def test_recovered_flow_without_check_scores_80_without_c3_permission(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                payload, diagnostics = self.payload(self.base(family, [FLOW + "."]))
                self.assertEqual(self.permissions(payload), {"c1": ["e001"], "c2": ["e001"], "c3": []})
                row = self.assessment(payload, diagnostics, {
                    "c1": ("e001", FLOW), "c2": ("e001", METHOD),
                })
                self.assertEqual((row["entry_level_score"], row["errors"]), (.8, []))
                # A real source quote cannot be reused as a check without permission.
                invalid = self.assessment(payload, diagnostics, {
                    "c1": ("e001", FLOW), "c2": ("e001", METHOD), "c3": ("e001", FLOW),
                })
                self.assertIsNone(invalid["entry_level_score"])
                self.assertIn("c3:proof_outside_fixed_criterion_candidates", invalid["errors"])

    def test_separate_check_bullet_is_recovered_but_core_and_metadata_are_not_checks(self):
        check = "I checked row counts after each run."
        for family in FAMILIES:
            with self.subTest(family=family):
                base = self.base(family, [FLOW + ".", check, "Supervisor: Verified records."])
                _, before = _selection._select_criteria(base)
                self.assertEqual(before["skills"]["data_pipelines"]["selected_activity_ids"], [])
                payload, diagnostics = self.payload(base)
                self.assertEqual(self.permissions(payload)["c3"], ["e002"])
                self.assertNotIn("e003", self.permissions(payload)["c2"])
                row = self.assessment(payload, diagnostics, {
                    "c1": ("e001", FLOW), "c2": ("e001", METHOD), "c3": ("e002", check),
                })
                self.assertEqual((row["entry_level_score"], row["errors"]), (1.0, []))
                self.assert_consistent_diagnostics(base, payload, diagnostics)

    def test_already_selected_activity_gets_children_after_its_personal_core_is_recovered(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                base = self.base(family, ["My teammate built an ETL pipeline.", COMPLETE])
                packet, before = _selection._select_criteria(base)
                self.assertEqual(before["skills"]["data_pipelines"]["selected_activity_ids"], ["a001"])
                self.assertEqual(packet["skills"]["data_pipelines"]["criterion_unit_ids"],
                                 {"c1": ["e001"], "c2": [], "c3": []})
                payload, diagnostics = self.payload(base)
                for cid in ("c1", "c2", "c3"):
                    self.assertIn("e002", self.permissions(payload)[cid])
                row = self.assessment(payload, diagnostics, {
                    "c1": ("e002", COMPLETE), "c2": ("e002", METHOD), "c3": ("e002", CHECK),
                })
                self.assertEqual((row["entry_level_score"], row["errors"]), (1.0, []))
                self.assert_consistent_diagnostics(base, payload, diagnostics)

    def test_check_from_another_unselected_activity_is_not_recovered(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                base = self.base(family, [FLOW + "."], ["I checked row counts after each run."])
                payload, diagnostics = self.payload(base)
                self.assertEqual(self.permissions(payload)["c3"], [])
                self.assertEqual(diagnostics["skills"]["data_pipelines"]["selected_activity_ids"], ["a001"])
                self.assert_consistent_diagnostics(base, payload, diagnostics)

    def test_check_plans_and_prepared_harnesses_do_not_gain_c3_permission(self):
        for family in FAMILIES:
            for check in ("I plan to check row counts.", "I prepared a test harness for checking row counts."):
                with self.subTest(family=family, check=check):
                    payload, _ = self.payload(self.base(family, [FLOW + ".", check]))
                    self.assertEqual(self.permissions(payload)["c3"], [])

    def test_recovery_retains_three_selected_activities_and_reports_omitted_flow(self):
        strong = "I built a scheduled ETL pipeline that moved records from the source into the warehouse."
        for family in FAMILIES:
            with self.subTest(family=family):
                base = self.base(family, [strong], [strong], [strong], [COMPLETE])
                payload, diagnostics = self.payload(base)
                detail = diagnostics["skills"]["data_pipelines"]
                self.assertEqual(detail["selected_activity_ids"], ["a001", "a002", "a003"])
                self.assertEqual(detail["omitted_plausible_activity_ids"], ["a004"])
                self.assertTrue(detail["search_incomplete"])
                self.assertEqual(detail["selection_state"], "plausible_activities_not_selected")
                self.assertNotIn("e004", self.permissions(payload)["c3"])
                self.assert_consistent_diagnostics(base, payload, diagnostics)
                row = self.assessment(payload, diagnostics, {})
                self.assertIsNone(row["entry_level_score"])
                self.assertEqual(row["calculation_state"], "needs_confirmation")

    def test_recovery_adds_only_one_open_slot_in_source_order_and_tracks_the_rest(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                base = self.base(family, [COMPLETE], [COMPLETE])
                payload, diagnostics = self.payload(base)
                detail = diagnostics["skills"]["data_pipelines"]
                self.assertEqual(detail["selected_activity_ids"], ["a001"])
                self.assertEqual(detail["omitted_plausible_activity_ids"], ["a002"])
                self.assertTrue(detail["search_incomplete"])
                self.assert_consistent_diagnostics(base, payload, diagnostics)

    def test_recovery_does_not_add_planned_negated_one_off_or_others_work(self):
        examples = (
            "I plan to move records from the vendor endpoint into the reporting store nightly.",
            "I never moved records from the vendor endpoint into the reporting store nightly.",
            "I moved records from the vendor endpoint into the reporting store once.",
            "My teammate moved records from the vendor endpoint into the reporting store nightly.",
        )
        for family in FAMILIES:
            for text in examples:
                with self.subTest(family=family, text=text):
                    base = self.base(family, [text])
                    before, _ = _selection._select_criteria(base)
                    after, _ = _selection.select(base)
                    self.assertEqual(before["skills"]["data_pipelines"], after["skills"]["data_pipelines"])
                    self.assertEqual(after["skills"]["data_pipelines"]["criterion_unit_ids"]["c1"], [])


if __name__ == "__main__":
    unittest.main()
