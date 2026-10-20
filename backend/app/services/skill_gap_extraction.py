"""Validate Agent citations, then compute scores and frequencies entirely in Python."""
import hashlib
import json
import re
from datetime import timedelta

from app.schemas.skill_gap import CandidateSkill, ConfirmedResume, MarketInput, MarketSkill
from app.schemas.skill_gap_extraction import (
    JobRequirementsExtraction, PostingDocument, PostingSnapshot, ResumeEvidenceExtraction,
    ReviewedResume, TargetScope,
)
from app.services.skill_gap import ALIASES, normalize_skill

EVIDENCE_SCORES = {"listed": 0.25, "applied": 0.6, "validated": 0.8}


def skill_is_explicit(skill: str, quote: str) -> bool:
    names = [skill] + [alias for alias, canonical in ALIASES.items()
                       if canonical.casefold() == skill.casefold()]
    return any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", quote, re.I) for name in names)


def select_postings(snapshot: PostingSnapshot, scope: TargetScope) -> tuple[list[PostingDocument], list[dict]]:
    selected, audit = [], []
    seen_ids, seen_content = {}, set()
    role_words = re.findall(r"\w+", scope.target_role.casefold())
    if not role_words:
        raise ValueError("Target role must contain words.")
    start = scope.as_of - timedelta(days=scope.window_days - 1)
    level_patterns = {
        "entry": r"\b(new[ -]?grad(?:uate)?s?|entry[ -]?level|junior|graduate)\b",
        "intern": r"\bintern(?:ship)?\b",
        "mid": r"\b(mid[ -]?level|engineer ii|developer ii)\b",
        "senior": r"\b(senior|staff|principal|lead)\b",
    }
    for document in snapshot.postings:
        posting = document.posting
        identity = document.posting_id
        serial = json.dumps(document.model_dump(mode="json"), sort_keys=True)
        if identity in seen_ids and seen_ids[identity] != serial:
            raise ValueError(f"Conflicting snapshots for {identity}; select one version first.")
        signature = hashlib.sha256("\n".join(
            " ".join(value.casefold().split()) for value in (
                document.company_name, posting.title, posting.location or "", posting.description_text,
            )
        ).encode()).hexdigest()
        title = " ".join(re.findall(r"\w+", posting.title.casefold()))
        reason = None
        if identity in seen_ids or signature in seen_content:
            reason = "duplicate"
        elif not all(word in title.split() for word in role_words):
            reason = "target_role_not_explicit_in_title"
        elif scope.seniority == "entry" and re.search(
            r"\b(senior|staff|principal|lead|manager|intern)\b", title,
        ):
            reason = "not_entry_level"
        elif not re.search(level_patterns[scope.seniority], title):
            reason = "seniority_not_explicit_in_title"
        elif posting.country != scope.country:
            reason = "country_not_matched_or_unknown"
        elif not posting.published_at:
            reason = "published_date_unknown"
        elif not start <= posting.published_at.date() <= scope.as_of:
            reason = "outside_publication_window"
        elif not posting.description_text.strip():
            reason = "empty_description"
        seen_ids[identity] = serial
        seen_content.add(signature)
        audit.append({"posting_id": identity, "title": posting.title,
                      "included": reason is None, "reason": reason or "included"})
        if reason is None:
            selected.append(document)
    if not selected:
        raise ValueError("No postings match the explicit title, seniority, country and date filters.")
    return selected, audit


def aggregate_market(extraction: JobRequirementsExtraction, documents: list[PostingDocument],
                     scope: TargetScope) -> tuple[MarketInput, list[dict]]:
    by_id = {item.posting_id: item for item in documents}
    extracted_ids = [item.posting_id for item in extraction.postings]
    if len(set(extracted_ids)) != len(extracted_ids) or set(extracted_ids) != set(by_id):
        raise ValueError("Agent must return exactly one extraction for every selected posting.")
    buckets: dict[str, dict] = {}
    for item in extraction.postings:
        description = by_id[item.posting_id].posting.description_text
        for requirement in item.skills:
            name = normalize_skill(requirement.skill)
            if requirement.quote not in description or not skill_is_explicit(name, requirement.quote):
                raise ValueError(f"Unverifiable job-skill citation for {item.posting_id}/{name}.")
            key = name.casefold()
            bucket = buckets.setdefault(key, {"skill": name, "required": set(), "preferred": set(),
                                               "citations": []})
            bucket["citations"].append({"posting_id": item.posting_id,
                                         **requirement.model_dump()})
            if requirement.requirement in ("required", "preferred"):
                bucket[requirement.requirement].add(item.posting_id)
    counts, skills = [], []
    total = len(documents)
    for bucket in sorted(buckets.values(), key=lambda x: x["skill"].casefold()):
        required = bucket["required"]
        # One posting counts once, even if a skill is both required and preferred.
        preferred = bucket["preferred"] - required
        matched = required | preferred
        counts.append({
            "skill": bucket["skill"], "postings": len(matched), "denominator": total,
            "required_postings": len(required), "preferred_only_postings": len(preferred),
            "frequency": len(matched) / total, "required_frequency": len(required) / total,
            "preferred_only_frequency": len(preferred) / total,
            "matched_posting_ids": sorted(matched), "citations": bucket["citations"],
        })
        if matched:
            examples = [f"{c['posting_id']}: {c['quote']}" for c in bucket["citations"]
                        if c["requirement"] in ("required", "preferred")]
            skills.append(MarketSkill(skill=bucket["skill"], frequency=len(matched) / total,
                                      examples=list(dict.fromkeys(examples))[:3]))
    companies = len({" ".join(d.company_name.casefold().split()) for d in documents})
    return MarketInput(target_role=scope.target_role, seniority=scope.seniority,
                       window_days=scope.window_days, sample_size=total, company_count=companies,
                       low_confidence=total < 30 or companies < 3 or not skills, skills=skills), counts


def resolve_pointer(document: dict, pointer: str):
    if not pointer.startswith("/"):
        raise ValueError("Evidence paths must be JSON pointers starting with '/'.")
    value = document
    try:
        for part in pointer[1:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9]\d*", key):
                    raise ValueError("Invalid array index.")
                value = value[int(key)]
            else:
                value = value[key]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("Evidence path does not exist in the reviewed résumé.") from None
    return value


def score_resume(extraction: ResumeEvidenceExtraction, resume: ReviewedResume,
                 expected_skills: list[str]) -> tuple[ConfirmedResume, list[dict]]:
    source = resume.classification.model_dump(exclude={"personal_information"})
    wanted = {normalize_skill(skill).casefold(): normalize_skill(skill) for skill in expected_skills}
    names = [normalize_skill(item.skill).casefold() for item in extraction.skills]
    if len(names) != len(set(names)) or set(names) != set(wanted):
        raise ValueError("Agent must return every requested résumé skill exactly once.")
    candidates, audit = [], []
    for item in extraction.skills:
        name = wanted[normalize_skill(item.skill).casefold()]
        best = 0.0
        validated_contexts = set()
        unique = set()
        citations = []
        for citation in item.citations:
            value = resolve_pointer(source, citation.path)
            if not isinstance(value, str) or citation.quote not in value or not skill_is_explicit(name, citation.quote):
                raise ValueError(f"Unverifiable résumé citation for {name}.")
            parts = citation.path.split("/")
            if citation.kind != "listed" and (
                len(parts) != 5 or parts[3] != "content" or parts[1] not in {
                    "projects", "work_experience", "research_experience", "education", "leadership_activities",
                }
            ):
                raise ValueError("Applied/validated evidence must cite an experience or project content field.")
            key = (citation.path, citation.quote, citation.kind)
            if key in unique:
                continue
            unique.add(key)
            citations.append(citation.model_dump())
            best = max(best, EVIDENCE_SCORES[citation.kind])
            if citation.kind == "validated":
                validated_contexts.add("/".join(parts[:3]))
        if len(validated_contexts) >= 2:
            best = 1.0
        candidates.append(CandidateSkill(skill=name, evidence_score=best,
                                         evidence=list(dict.fromkeys(c["quote"] for c in citations))))
        audit.append({"skill": name, "evidence_score": best, "citations": citations,
                      "validated_context_count": len(validated_contexts),
                      "interpretation": "résumé evidence coverage, not verified ability"})
    return ConfirmedResume(confirmed=True, candidate_skills=candidates), audit
