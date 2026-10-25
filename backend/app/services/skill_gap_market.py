"""Read the frozen demand snapshot for display; no Agent or database needed."""
import json
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.schemas.skill_gap_web import JobFamily

SNAPSHOT_ROOT = BACKEND_ROOT / "local_experiments" / "skill_gap_core_v12"


def get_market_demand(family: JobFamily, root: Path = SNAPSHOT_ROOT) -> dict:
    catalog = json.loads((root / "core_catalog.json").read_text(encoding="utf-8"))
    market = json.loads((root / "market_snapshot.json").read_text(encoding="utf-8"))
    source = market["families"][family]
    count = source["total_job_count"]
    skills = [dict(skill_id=skill["skill_id"], module_id=module["module_id"], N=count,
                   **source["skills"][skill["skill_id"]])
              for module in catalog["families"][family]["modules"] for skill in module["skills"]]
    return {"job_family": family, "sample_size": count, "core_skill_count": len(skills),
            "source_analysis_version": market["source_analysis_version"],
            "snapshot_fingerprint": market["source_fingerprint"], "skills": skills,
            "responsibilities_available": False, "common_responsibilities": [], "database_used": False}
