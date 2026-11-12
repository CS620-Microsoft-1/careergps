"""Try project recommendations without the app: no login, résumé or skill-gap run needed.

Run from backend/:
    python -m scripts.try_projects --list-skills ai_engineer
    python -m scripts.try_projects ai_engineer rag ai_agents mlops
    python -m scripts.try_projects data_analyst dashboarding sql --hours 25
    python -m scripts.try_projects software_engineer frontend testing --agent

Skill gaps are skill ids from the role's catalog, highest priority first (--list-skills shows
them). Without --agent it uses the free rule ranking; --agent calls the Foundry resources agent
(needs RESOURCES_PROJECT_ENDPOINT in .env and `az login`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resources import FAMILY_TO_CATALOG, load_projects  # noqa: E402
from app.services.resources_agent import _candidates, _shortlist, rank_projects, recommend_projects  # noqa: E402
from app.services.skill_gaps.assets import ASSET_ROOT  # noqa: E402


def catalog_skills(family: str) -> dict[str, dict]:
    catalog = json.loads((ASSET_ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    return {skill["skill_id"]: skill for module in catalog["families"][family]["modules"] for skill in module["skills"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("family", choices=sorted(FAMILY_TO_CATALOG))
    parser.add_argument("skill_ids", nargs="*", help="skill gaps, highest priority first")
    parser.add_argument("--hours", type=int, default=None, help="time budget in hours")
    parser.add_argument("--agent", action="store_true", help="ask the Foundry resources agent instead of the rules")
    parser.add_argument("--list-skills", action="store_true", help="print the role's skill ids and exit")
    args = parser.parse_args()

    skills = catalog_skills(args.family)
    if args.list_skills or not args.skill_ids:
        for skill_id, skill in skills.items():
            print(f"{skill_id:28} {skill['skill_name']}")
        return 0
    unknown = [s for s in args.skill_ids if s not in skills]
    if unknown:
        print(f"Unknown skill ids for {args.family}: {unknown}. Use --list-skills.")
        return 1

    gaps = [{"skill_id": s, "skill_name": skills[s]["skill_name"], "definition": skills[s]["definition"]}
            for s in args.skill_ids]
    names = [gap["skill_name"] for gap in gaps]
    career_path = FAMILY_TO_CATALOG[args.family]
    pool = [p for p in load_projects() if p["career_path"] == career_path]
    candidates = _candidates(career_path, args.hours, gaps)
    print(f"{career_path}: {len(pool)} projects in catalog "
          f"({sum(p.get('source') == 'github' for p in pool)} from GitHub), {len(candidates)} match these gaps")
    if args.agent:
        print(f"Asking the agent with the top {len(_shortlist(candidates, gaps, names))} candidates...")
        result = {**recommend_projects(career_path, [], names, args.hours, gaps), "source": "agent"}
    else:
        result = {**rank_projects(career_path, [], names, args.hours, gaps), "source": "rules"}

    print(f"\nRecommendations ({result['source']}):")
    if not result["recommendations"]:
        print("  none:", result["no_match_reason"])
    for index, item in enumerate(result["recommendations"], 1):
        project = item["project"]
        origin = "GitHub" if project.get("source") == "github" else "hand-written"
        print(f"\n{index}. {project['title']}  [{origin}, {project['difficulty']}, ~{project['estimated_hours']}h]")
        print(f"   closes: {', '.join(item['addressed_gaps'])}")
        print(f"   why:    {item['why_recommended']}")
        if project.get("url"):
            print(f"   link:   {project['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
