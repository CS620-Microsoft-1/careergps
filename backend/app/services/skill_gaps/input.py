"""Build the single-call input from an immutable reviewed resume snapshot."""
from .schema import SCHEMA_NAME
from .sources import build_sources


def prepare(family, resume, resume_id, catalog):
    return {
        "task": "extract_resume_evidence", "job_family": family, "resume_id": resume_id, "evidence_contract": SCHEMA_NAME,
        "resume_sources": build_sources(resume),
        "core_skills": [{**skill, "module_id": module["module_id"]}
                        for module in catalog["families"][family]["modules"]
                        for skill in module["skills"]],
    }
