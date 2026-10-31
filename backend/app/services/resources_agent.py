import json

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from app.core.config import get_settings
from app.schemas.resources import ResourceRecommendations
from app.services.resources import load_projects


MAX_PROJECTS = 3


def _candidates(career_path: str, available_hours: int | None,
                verified_skill_gaps: list[dict[str, str]] | None) -> list[dict]:
    """Approved projects for the career path, within the time budget and touching a verified gap."""
    candidates = [
        project
        for project in load_projects()
        if project["career_path"] == career_path
        and (available_hours is None or project["estimated_hours"] <= available_hours)
    ]
    if verified_skill_gaps is not None:
        ids = {item["skill_id"] for item in verified_skill_gaps}
        candidates = [p for p in candidates if ids.intersection(p.get("supported_skill_ids", []))]
    return candidates


def rank_projects(
    career_path: str,
    existing_skills: list[str],
    skill_gaps: list[str],
    available_hours: int | None = None,
    verified_skill_gaps: list[dict[str, str]] | None = None,
) -> dict:
    """The free fallback: greedy cover of the verified gaps, higher-priority gaps weighing more.

    verified_skill_gaps is in priority order. Same response shape as recommend_projects.
    """
    gaps = verified_skill_gaps or []
    weight = {gap["skill_id"]: len(gaps) - index for index, gap in enumerate(gaps)}
    names = {gap["skill_id"]: gap["skill_name"] for gap in gaps}
    remaining = _candidates(career_path, available_hours, gaps)
    covered: set[str] = set()
    recommendations = []
    while remaining and len(recommendations) < MAX_PROJECTS:
        def gain(project: dict) -> int:
            return sum(weight[skill] for skill in set(project["supported_skill_ids"]) & weight.keys() - covered)
        best = max(remaining, key=lambda project: (gain(project), -remaining.index(project)))
        if gain(best) <= 0:
            break
        skill_ids = [gap["skill_id"] for gap in gaps if gap["skill_id"] in best["supported_skill_ids"]]
        matched = [names[skill] for skill in skill_ids]
        recommendations.append({
            "project_id": best["id"], "addressed_gaps": matched, "addressed_skill_ids": skill_ids,
            "why_recommended": "This project provides practice in: " + ", ".join(matched) + ".",
            "prerequisites_to_check": list(best.get("prerequisites", [])), "project": best,
        })
        covered.update(skill_ids)
        remaining.remove(best)
    return {
        "recommendations": recommendations,
        "no_match_reason": None if recommendations else "No projects match the career path, skill gaps, and time budget.",
    }


def recommend_projects(
    career_path: str,
    existing_skills: list[str],
    skill_gaps: list[str],
    available_hours: int | None = None,
    verified_skill_gaps: list[dict[str, str]] | None = None,
) -> dict:
    settings = get_settings()

    if not settings.resources_project_endpoint:
        raise ValueError("RESOURCES_PROJECT_ENDPOINT is not configured.")

    candidates = _candidates(career_path, available_hours, verified_skill_gaps)
    if not candidates:
        return {"recommendations": [], "no_match_reason": "No projects match the career path, skill gaps, and time budget."}

    payload = {
        "career_path": career_path,
        "existing_skills": existing_skills,
        "skill_gaps": skill_gaps,
        "available_hours": available_hours,
        "candidate_projects": candidates,
    }
    if verified_skill_gaps is not None:
        payload["verified_skill_gaps"] = verified_skill_gaps
        payload["matching_rule"] = "Only claim a gap when its skill_id is in the project's supported_skill_ids. The definition specifies what that skill means."

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=settings.resources_project_endpoint,
            credential=credential,
            allow_preview=True,
        ) as project_client,
        # No SDK retries (it defaults to 2): a retry after a 120 s timeout runs after the browser has
        # given up and usually times out again. The route falls back to the rule ranking instead.
        project_client.get_openai_client(
            agent_name=settings.resources_agent_name,
            timeout=120,
            max_retries=0,
        ) as client,
    ):
        conversation = client.conversations.create()

        try:
            response = client.responses.create(
                conversation=conversation.id,
                input=[
                    {
                        "role": "user",
                        "content": json.dumps(payload),
                    }
                ],
            )

            if response.status != "completed":
                raise ValueError("The resources agent did not complete.")

            result = json.loads(response.output_text)
        finally:
            try:
                client.conversations.delete(
                    conversation_id=conversation.id
                )
            except Exception:
                pass

        validated = ResourceRecommendations.model_validate(result)

    allowed_projects = {project["id"]: project for project in candidates}
    seen_ids = set()

    recommendations = []
    for recommendation in validated.recommendations:
        project_id = recommendation.project_id

        if project_id not in allowed_projects:
            raise ValueError("Agent recommended a project outside the catalog.")

        if project_id in seen_ids:
            raise ValueError("Agent returned a duplicate project.")

        if not set(recommendation.addressed_gaps).issubset(set(skill_gaps)):
            raise ValueError("Agent returned a skill gap that was not supplied.")

        if (
            available_hours is not None
            and allowed_projects[project_id]["estimated_hours"] > available_hours
        ):
            raise ValueError("Agent recommended a project over the time budget.")

        seen_ids.add(project_id)

    for recommendation in validated.recommendations:
        project = allowed_projects[recommendation.project_id]
        item = recommendation.model_dump()
        if verified_skill_gaps is not None:
            supported = set(project.get("supported_skill_ids", []))
            by_name = {gap["skill_name"]: gap["skill_id"] for gap in verified_skill_gaps}
            matched = [name for name in item["addressed_gaps"] if by_name.get(name) in supported]
            if not matched:
                continue
            item["addressed_gaps"] = matched
            item["addressed_skill_ids"] = [by_name[name] for name in matched]
            item["prerequisites_to_check"] = [p for p in item["prerequisites_to_check"] if p in project.get("prerequisites", [])]
            item["why_recommended"] = "This project provides practice in: " + ", ".join(matched) + "."
        else:
            supported_names = {name.casefold() for name in project.get("skills_practiced", [])}
            matched = [name for name in item["addressed_gaps"] if name.casefold() in supported_names]
            if not matched:
                continue
            item["addressed_gaps"] = matched
            item["prerequisites_to_check"] = [p for p in item["prerequisites_to_check"] if p in project.get("prerequisites", [])]
            item["why_recommended"] = "This project provides practice in: " + ", ".join(matched) + "."
        recommendations.append({**item, "project": project})
    if not recommendations and validated.recommendations:
        # Picks that all claim unsupported gaps are a failed answer, not "nothing fits".
        raise ValueError("No agent pick practices a verified skill gap.")

    return {
        "recommendations": recommendations,
        "no_match_reason": None if recommendations else (validated.no_match_reason or "No projects matched the verified skill gaps."),
    }
