"""Replay job-seniority demand changes without changing frozen skill scores.

The default command is offline and reads the packaged aggregate counts. Raw
source replay is optional and requires an explicit, separately supplied ZIP.
No model, database, application configuration, or runtime snapshot is changed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[2]
COHORTS = {
    "entry_only": ("new_grad", "entry_level"),
    "entry_plus_intern": ("new_grad", "entry_level", "intern"),
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def filter_cohort(parents, qualifications, levels):
    """Use exact existing labels; unknown and mixed-level labels do not match."""
    selected = [row for row in parents if row.get("seniority") in levels]
    ids = {row["job_posting_id"] for row in selected}
    children = [row for row in qualifications if row["job_posting_id"] in ids]
    return selected, children


def reweight(case, market):
    """Change only demand and priority fields on an anonymous frozen case."""
    result = deepcopy(case)
    family = market["families"][case["job_family"]]
    n = family["total_job_count"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("The family denominator must be a nonnegative integer.")
    ids = [row["skill_id"] for row in case["skills"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Frozen skill IDs must be unique.")
    for row in result["skills"]:
        strength = row["evidence_strength"]
        if strength is not None and (isinstance(strength, bool) or not isinstance(strength, (float, int)) or not 0 <= strength <= 1):
            raise ValueError("Frozen strength must be a number in [0, 1] or null.")
        gap = None if strength is None else Decimal(1) - Decimal(str(strength))
        if row["gap"] != (None if gap is None else float(gap)):
            raise ValueError("Frozen gap differs from one minus strength.")
        if (row["grade"] is None) != (strength is None):
            raise ValueError("Frozen pending grade and strength disagree.")
        counts = family["skills"][row["skill_id"]]
        requested = counts["required_job_count"] + counts["preferred_only_job_count"]
        if requested < 0 or requested > n:
            raise ValueError("Required and preferred-only counts exceed the denominator.")
        weight = Decimal(requested) / Decimal(n) if n else Decimal(0)
        row["demand"] = {**counts, "N": n}
        row["demand_weight"] = round(float(weight), 6)
        row["priority"] = None if gap is None else round(float(weight * gap), 6)
    result["pending_skills"] = [row["skill_id"] for row in result["skills"] if row["evidence_strength"] is None]
    result["priority_order"] = [row["skill_id"] for row in sorted(
        (row for row in result["skills"] if row["priority"] is not None and row["priority"] > 0),
        key=lambda row: (-row["priority"], row["skill_id"]))]
    return result


def summarize_match(report):
    """Preserve the production weighted-match arithmetic and pending exclusion."""
    earned = total = Decimal(0)
    scored = 0
    for row in report["skills"]:
        strength = row["evidence_strength"]
        demand = row["demand"]
        if strength is None or demand["N"] <= 0:
            continue
        weight = Decimal(demand["required_job_count"] + demand["preferred_only_job_count"]) / Decimal(demand["N"])
        if weight <= 0:
            continue
        earned += weight * Decimal(str(strength))
        total += weight
        scored += 1
    if total == 0:
        return None
    return {"score": float(round(earned / total, 4)), "scored_skill_count": scored,
            "unscored_skill_count": sum(row["evidence_strength"] is None for row in report["skills"])}


def compare(cases, markets):
    summaries = []
    for case in cases:
        baseline = summarize_match(reweight(case, markets["all_levels"]))
        frozen = [(row["skill_id"], row["evidence_strength"], row["gap"], row["grade"]) for row in case["skills"]]
        cohorts = {}
        for name, market in markets.items():
            report = reweight(case, market)
            current = [(row["skill_id"], row["evidence_strength"], row["gap"], row["grade"]) for row in report["skills"]]
            if frozen != current:
                raise ValueError("Demand reweighting changed a frozen assessment.")
            match = summarize_match(report)
            delta = None if match is None or baseline is None else round((match["score"] - baseline["score"]) * 100, 4)
            cohorts[name] = {"match": match, "delta_percentage_points": delta,
                             "changed_skill_grades": 0, "changed_evidence_scores": 0}
        summaries.append({"case_id": case["case_id"], "job_family": case["job_family"], "cohorts": cohorts})
    return summaries


def replay_source(path):
    """Recount a supplied archive with the repository's existing demand rules."""
    sys.path.insert(0, str(BACKEND))
    from scripts.demand_snapshot import read_source, replay, snapshot_from_analysis

    parents, qualifications, source = read_source(source_zip=Path(path))
    analysis = replay(parents, qualifications, source=source)
    markets = {"all_levels": snapshot_from_analysis(analysis, source_sha256=canonical_digest(analysis))}
    cohorts = {}
    for name, levels in COHORTS.items():
        selected, children = filter_cohort(parents, qualifications, levels)
        scope = {**source, "seniority_filter": list(levels),
                 "selected_ids_sha256": canonical_digest(sorted(row["job_posting_id"] for row in selected))}
        analysis = replay(selected, children, source=scope)
        snapshot = snapshot_from_analysis(analysis, source_sha256=canonical_digest(analysis))
        markets[name] = snapshot
        cohorts[name] = {"levels": list(levels), "selected_source_parents": len(selected),
                         "excluded_null_family": sum(row.get("job_family") is None for row in selected),
                         "supported_families": {family: values["total_job_count"] for family, values in snapshot["families"].items()},
                         "selected_qualification_rows": len(children),
                         "unresolved_requirement_review_items": analysis["quality"]["review_items"]}
    return markets, cohorts, source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, help="Optionally recount a separately supplied source archive.")
    parser.add_argument("--output", type=Path, help="Write a new report; an existing file is never overwritten.")
    args = parser.parse_args(argv)
    saved = load(ROOT / "results.json")
    cases = load(ROOT / "fixtures/frozen_scores.json")["cases"]
    if args.source_zip:
        markets, counts, source = replay_source(args.source_zip)
        reference_data = source.get("source_sha256") == saved["source"]["archive_sha256"]
        if reference_data and any(markets[name]["families"] != saved["demand_snapshots"][name]["families"] for name in markets):
            raise ValueError("The historical archive produced different counts; inspect demand-rule drift before comparing results.")
    else:
        markets, counts = saved["demand_snapshots"], saved["cohort_counts"]
        source = {"source_kind": "packaged_aggregate_snapshots", "archive_sha256": saved["source"]["archive_sha256"]}
        reference_data = True
    comparisons = compare(cases, markets)
    if reference_data and comparisons != saved["case_comparisons"]:
        raise ValueError("The replay differs from the frozen historical comparison.")
    report = {"mode": "source_replay" if args.source_zip else "aggregate_replay", "source": source,
              "new_agent_calls": 0, "database_access": False, "runtime_changes": False,
              "historical_reference_matches": reference_data, "cohort_counts": counts,
              "case_comparisons": comparisons, "limitations": saved["limitations"]}
    if args.output:
        save_new(args.output, report)
    print("Case | Family | All levels | Entry only | Entry plus intern")
    for case in comparisons:
        values = [case["cohorts"][name]["match"] for name in ("all_levels", *COHORTS)]
        scores = ["pending" if value is None else f"{value['score'] * 100:.2f}%" for value in values]
        print(" | ".join([case["case_id"], case["job_family"], *scores]))
    print("All frozen skill scores, gaps, grades and pending states are unchanged.")
    print("No model or database calls. This is demand sensitivity, not accuracy validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
