import json

from app.services.resources_agent import recommend_projects


if __name__ == "__main__":
    result = recommend_projects(
        career_path="Software Engineering",
        existing_skills=[
            "JavaScript basics",
            "HTML and CSS basics",
        ],
        skill_gaps=["React", "REST APIs", "SQL", "testing"],
        available_hours=25,
    )

    print(json.dumps(result, indent=2))