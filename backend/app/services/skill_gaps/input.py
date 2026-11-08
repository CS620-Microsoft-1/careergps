"""Build evidence input with stable core cards before dynamic resume data."""
from .core_cards import CoreSkillCards
from .schema import SCHEMA_NAME
from .sources import build_sources


def prepare(family, resume, resume_id, catalog, *, core_cards=None):
    cards = core_cards if core_cards is not None else CoreSkillCards(catalog)
    return {
        "task": "extract_resume_evidence", "job_family": family, "evidence_contract": SCHEMA_NAME,
        "core_skills": cards.for_family(family, catalog=catalog),
        "resume_id": resume_id,
        "resume_sources": build_sources(resume),
    }
