import json

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from app.core.config import BACKEND_ROOT, get_settings
from app.schemas.resources import ResourceRecommendations


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

    # Read the approved project catalog.
    catalog_path = BACKEND_ROOT / "data" / "projects.json"
    projects = json.loads(catalog_path.read_text(encoding="utf-8"))

    # Send only projects for the selected career path.
    candidates = [
        project
        for project in projects
        if project["career_path"] == career_path
        and (available_hours is None or project["estimated_hours"] <= available_hours)
    ]

    if verified_skill_gaps is not None:
        ids = {item["skill_id"] for item in verified_skill_gaps}
        candidates = [p for p in candidates if ids.intersection(p.get("supported_skill_ids", []))]
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
        project_client.get_openai_client(
            agent_name=settings.resources_agent_name,
            timeout=120,
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

    return {
        "recommendations": recommendations,
        "no_match_reason": None if recommendations else (validated.no_match_reason or "No projects matched the verified skill gaps."),
    }
