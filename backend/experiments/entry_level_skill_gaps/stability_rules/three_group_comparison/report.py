"""Compare the two native scoring reports without exporting resume evidence."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from app.services.skill_gaps.match import summarize_match
from app.services.skill_gaps.skill_groups import GROUP_SKILLS
from experiments.entry_level_skill_gaps.entry_agents.run_experiment import read, save_new


def comparison(root):
    arms = {name: read(root / "runs" / name / "summary.json") for name in ("original", "entry")}
    result = {"arms": arms, "complete": all(arm["complete"] for arm in arms.values()),
              "isolation": read(root / "isolation_check.json")}
    if not result["complete"]:
        return result
    native, entry = (read(root / "runs" / arm / "report.json") for arm in ("original", "entry"))
    if native["job_family"] != entry["job_family"] or native["demand_snapshot_fingerprint"] != entry["demand_snapshot_fingerprint"]:
        raise ValueError("Both reports must use the same family and all-job demand snapshot")
    family = native["job_family"]
    groups = {sid: group for group, ids in GROUP_SKILLS[family].items() for sid in ids}
    rows = {arm: {row["skill_id"]: row for row in report["skills"]}
            for arm, report in (("original", native), ("entry", entry))}
    if any(set(side) != set(groups) for side in rows.values()):
        raise ValueError("Both arms must contain each assigned skill exactly once")
    weights, differences = {}, []
    for sid, a in rows["original"].items():
        b = rows["entry"][sid]
        d = a["demand"]
        if d != b["demand"]:
            raise ValueError("Demand counts changed for an assigned skill")
        weights[sid] = Decimal(d["required_job_count"] + d["preferred_only_job_count"]) / Decimal(d["N"])
        first, second = a["resume_evidence_strength"], b["resume_evidence_strength"]
        differences.append({"skill_id": sid, "skill_name": a["skill_name"], "group": groups[sid],
                            "original_score": first, "entry_score": second,
                            "original_grade": a["skill_gap_grade"], "entry_grade": b["skill_gap_grade"],
                            "delta_points": round((second - first) * 100, 2) if first is not None and second is not None else None,
                            "original_pending_reason": a.get("scoring_breakdown", {}).get("reason") if first is None else None,
                            "entry_pending_reasons": b.get("errors", []) if second is None else [],
                            "demand_weight": float(weights[sid]), "demand": d})
    common = [r["skill_id"] for r in differences if r["delta_points"] is not None]
    total_weight = sum(weights.values())
    result.update(job_family=family, skill_count=len(differences), all_job_count=differences[0]["demand"]["N"],
                  demand_snapshot_fingerprint=native["demand_snapshot_fingerprint"],
                  common_scored_skills=common, skill_scores=differences,
                  common_demand_coverage=float(sum(weights[sid] for sid in common) / total_weight),
                  common_match={arm: summarize_match({"skills": [side[sid] for sid in common]})
                                for arm, side in rows.items()},
                  scored_demand_coverage={arm: float(sum(weights[sid] for sid, row in side.items()
                                                         if row["resume_evidence_strength"] is not None) / total_weight)
                                          for arm, side in rows.items()},
                  match={arm: summarize_match({"skills": list(side.values())}) for arm, side in rows.items()},
                  limits=["Single paired observation on one previously used resume.",
                          "Original evidence strength and entry criterion coverage use different rubrics.",
                          "Original Agents receive all resume sources. Entry Agents receive the frozen selected evidence packets.",
                          "Human evidence selection, resume parsing and database time are outside the measured wall time."])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = comparison(args.directory.resolve())
    save_new(args.output, result)
    print(json.dumps({k: result[k] for k in ("complete", "match", "common_match", "scored_demand_coverage") if k in result}, indent=2))
