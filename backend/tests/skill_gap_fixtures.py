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


def group_settings(**changes):
    """Explicit offline bindings; no developer env or Azure request is needed."""
    from app.core.config import SkillGapSettings
    from app.services.skill_gaps.skill_groups import GROUPS
    values = {"skill_gap_foundry_project_endpoint": "https://fixture.invalid/api/projects/test",
        **{f"skill_gap_{group}_agent_name": f"fixture-{group}" for group in GROUPS},
        **{f"skill_gap_{group}_agent_version": "1" for group in GROUPS}}
    values.update(changes)
    return SkillGapSettings(_env_file=None, **values)


def group_preflight(groups, save, *, settings):
    """A pure saved-version snapshot implementing the production injection API."""
    from app.services.skill_gaps.skill_group_transport import (
        PreparedGroup, _load_local_contract, _check_definition,
    )
    result = {}
    for group in groups:
        instructions, format_, prompt_hash, schema_hash, _ = _load_local_contract(group)
        version = getattr(settings, f"skill_gap_{group}_agent_version") or "1"
        if version == "latest":
            version = "1"
        name = getattr(settings, f"skill_gap_{group}_agent_name")
        definition = {"kind": "prompt", "model": "fixture-model",
            "instructions": instructions, "reasoning": {"effort": "medium"},
            "text": {"format": {"type": "json_schema", **format_}}}
        check = _check_definition(group, definition, version, instructions, format_, save,
            instructions_hash=prompt_hash, schema_file_hash=schema_hash)
        save(group, "observed_agent.json", {"branch": group, "name": name,
            "version": version, "definition": definition, "draft": False})
        result[group] = PreparedGroup(group, settings.skill_gap_foundry_project_endpoint,
            name, version, definition, check)
    return result


def group_manager(directory, invoker=None, **changes):
    """Construct the actual three-group manager with synthetic transport only."""
    from app.services.skill_gaps.runs import SkillGapRunManager
    def empty(payload, save, on_request, timings):
        on_request()
        return absent_response(payload)
    options = {"settings": group_settings(), "group_preflight": group_preflight,
               "invoker": invoker or empty}
    options.update(changes)
    return SkillGapRunManager(directory, **options)
