"""Synthetic Skill Gap inputs; no personal data, saved runs or external files."""
from datetime import datetime, timezone
from uuid import UUID

from app.schemas.resume import ResumeClassification

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
RESUME_ID = UUID("22222222-2222-4222-8222-222222222222")
CONFIRMED_AT = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def reviewed_resume():
    data = {name: [] for name in ResumeClassification.model_fields if name != "personal_information"}
    data["personal_information"] = {"name": "Alex Example", "emails": ["alex@example.invalid"],
        "phones": [], "location": None, "linkedin": None, "github": None, "website": None}
    data["technical_skills"] = ["Python", "SQL"]
    data["projects"] = [{"name": "Sample API", "url": None, "technologies": ["Python"],
                         "content": ["Implemented an API in Python and checked its output with unit tests."]}]
    return ResumeClassification.model_validate(data).model_dump(mode="json")


def absent_response(payload):
    return {"task": "extract_resume_evidence", "result": {"job_family": payload["job_family"],
            **{skill["skill_id"]: {"kind": "absent"} for skill in payload["core_skills"]}}}
