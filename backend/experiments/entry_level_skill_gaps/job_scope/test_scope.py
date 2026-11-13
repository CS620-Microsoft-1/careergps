"""Check the frozen historical replay and the boundaries of scope changes."""
from copy import deepcopy
import unittest

from run_comparison import COHORTS, ROOT, compare, filter_cohort, load, reweight, summarize_match


class JobScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = load(ROOT / "results.json")
        cls.cases = load(ROOT / "fixtures/frozen_scores.json")["cases"]
        cls.markets = cls.saved["demand_snapshots"]

    def test_all_eighteen_historical_case_cohort_results_replay_exactly(self):
        self.assertEqual(compare(self.cases, self.markets), self.saved["case_comparisons"])

    def test_scope_change_preserves_scores_grades_pending_and_input(self):
        before = deepcopy(self.cases)
        for case in self.cases:
            frozen = [(r["skill_id"], r["evidence_strength"], r["gap"], r["grade"]) for r in case["skills"]]
            pending = [r["skill_id"] for r in case["skills"] if r["evidence_strength"] is None]
            for market in self.markets.values():
                report = reweight(case, market)
                self.assertEqual(frozen, [(r["skill_id"], r["evidence_strength"], r["gap"], r["grade"]) for r in report["skills"]])
                self.assertEqual(pending, report["pending_skills"])
        self.assertEqual(before, self.cases)

    def test_exact_seniority_filter_excludes_unknown_and_mixed_labels(self):
        labels = ["new_grad", "entry_level", "intern", None, "entry_level,senior", "senior"]
        parents = [{"job_posting_id": str(i), "seniority": label} for i, label in enumerate(labels)]
        children = [{"job_posting_id": str(i), "value": "example"} for i in range(len(labels))]
        for name, expected in [("entry_only", ["0", "1"]), ("entry_plus_intern", ["0", "1", "2"])]:
            selected, qualifications = filter_cohort(parents, children, COHORTS[name])
            self.assertEqual(expected, [r["job_posting_id"] for r in selected])
            self.assertEqual(expected, [r["job_posting_id"] for r in qualifications])

    def test_zero_demand_is_not_a_zero_skill_score(self):
        case = deepcopy(self.cases[0])
        market = deepcopy(self.markets["all_levels"])
        family = market["families"][case["job_family"]]
        for row in family["skills"].values():
            row["required_job_count"] = row["preferred_only_job_count"] = 0
        report = reweight(case, market)
        self.assertIsNone(summarize_match(report))
        self.assertEqual([], report["priority_order"])
        self.assertEqual([r["evidence_strength"] for r in case["skills"]], [r["evidence_strength"] for r in report["skills"]])

    def test_inconsistent_frozen_gap_is_rejected(self):
        case = deepcopy(self.cases[0])
        scored = next(row for row in case["skills"] if row["evidence_strength"] is not None)
        scored["gap"] = 2
        with self.assertRaisesRegex(ValueError, "Frozen gap"):
            reweight(case, self.markets["all_levels"])


if __name__ == "__main__":
    unittest.main()
