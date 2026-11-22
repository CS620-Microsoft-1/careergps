"""Production contract for the evidence-first entry-level skill gap workflow."""

from functools import lru_cache

from app.services.skill_gaps.match import summarize_match
from app.services.skill_gaps.skill_groups import GROUPS, GROUP_SKILLS, make_group_payloads
from app.services.skill_gaps.sources import build_index

from . import _lifecycle, _rubric, _selection, _systems
from ._proofs import normalize_output, reference_consumers, repair_output
from ._review import _localize, guard_assessment, review_assessment, structural_errors


RUNTIME_VERSION = "entry-level-evidence-recall.v1"
_AI_ADAPTERS = {"foundation": _rubric, "lifecycle": _lifecycle, "systems": _systems}


def _adapter(group, family):
    if group not in GROUPS or family not in GROUP_SKILLS:
        raise ValueError("Unknown skill group or family")
    return _AI_ADAPTERS[group] if family == "ai_engineer" else _rubric


def build_format(group, family):
    """Build the response schema for the pinned Agent and its assigned skills."""
    return _adapter(group, family).build_format(group, family)


def validate_payload(group, payload):
    """Validate source permissions and group scope before Agent invocation."""
    family = payload["job_family"]
    validated = _adapter(group, family).validate_payload(payload)
    if validated[:2] != (family, group):
        raise ValueError("The requested group must match the validated payload scope")
    return validated


@lru_cache(maxsize=1)
def _signature():
    return _rubric.sha({
        "runtime": RUNTIME_VERSION,
        "selector": _selection.SELECTOR_VERSION,
        "contract": _rubric.CONTRACT_VERSION,
        "validation": _rubric.VALIDATION_VERSION,
        "rules": {family: _rubric._rule_document(family) for family in GROUP_SKILLS},
        "formats": {family: {group: build_format(group, family) for group in GROUPS}
                    for family in GROUP_SKILLS},
    })


def signature():
    """Identify the deployed scoring, schema and rule versions for cache keys."""
    return _signature()


def prepare_group_inputs(base_input):
    """Prepare the three independently authorized inputs from confirmed data."""
    packet, diagnostics = _selection.select(base_input)
    family = base_input["job_family"]
    groups = make_group_payloads(base_input)
    return ({
        group: _adapter(group, family).build_payload(groups[group], packet)
        for group in GROUPS
    }, diagnostics)


def absent_group_output(payload):
    """Represent no supplied candidates with the assigned Agent's exact schema."""
    family = payload["job_family"]
    group = payload["evidence_scope"]["branch"]
    schemas = build_format(group, family)["schema"]["properties"]["result"]["properties"]
    result = {"job_family": family}
    for skill in payload["evidence_scope"]["assigned_skill_ids"]:
        fields = schemas[skill]["properties"]
        if "criteria" in fields:
            criteria = [
                {"criterion_id": cid, "status": "not_evidenced", "basis": "none", "proof_ids": []}
                for cid in (_rubric.CRITERION_IDS[:2] if "check_facts" in fields else _rubric.CRITERION_IDS)
            ]
            result[skill] = {"criteria": criteria}
        if "check_facts" in fields:
            result[skill]["check_facts"] = {
                "event": "absent", "workload_link": "not_applicable", "action": "",
                "checked_output": "", "detail": "", "proof_ids": [],
            }
        if "core_facts" in fields:
            if skill == "rag":
                facts = {"personal_retrieval": "absent", "model_generation": "not_stated",
                         "retrieval_use": "absent"}
            else:
                facts = {"execution": "absent", "ownership": "not_applicable"}
                if skill == "vector_retrieval":
                    facts = {"claim_kind": "absent", "execution": "not_applicable",
                             "method": "not_applicable", "ownership": "not_applicable"}
                elif skill == "fine_tuning":
                    facts.update(pretrained_origin="not_applicable", parameter_update="not_applicable")
                else:
                    facts["serving_identity"] = "not_applicable"
            result[skill] = {"core_facts": {**facts, "workload_link": "not_applicable", "proof_ids": []},
                             "children": None}
    output = {"task": payload["task"], "result": result, "proofs": []}
    if family == "ai_engineer" and group == "systems":
        output["partial_core"] = dict.fromkeys(_systems.TARGETS)
    return output


def _assess_response(group, output, payload, schema):
    family = payload["job_family"]
    adapter = _adapter(group, family)
    if group == "foundation":
        return adapter.assess_output(output, payload)
    normalized, aliases = normalize_output(output, payload, schema,
                                           partial_core=(family == "ai_engineer" and group == "systems"))
    assessment = adapter.assess_output(normalized, payload)
    if family != "ai_engineer":
        _lifecycle.apply_shared_proof_policy(assessment, normalized)
        assessment["raw_response_sha256"] = _rubric.sha(output)
    if aliases:
        raw_sha = _rubric.sha(output)
        assessment["raw_response_sha256"] = raw_sha
        assessment["proof_deduplication"] = {
            "aliases": aliases,
            "raw_response_sha256": raw_sha,
            "normalized_response_sha256": _rubric.sha(normalized),
        }
        assessment["validation"]["raw_output_modified"] = False
    return assessment


def _citation_counts(output, payload):
    proofs = {proof["proof_id"]: proof for proof in output["proofs"]}
    unique_ids = len(proofs) == len(output["proofs"])
    units = build_index(payload["resume_sources"])
    packets = payload["fixed_evidence_packets"]["skills"]
    counts = dict.fromkeys(("references", "exact", "authorized", "exact_and_authorized"), 0)
    for proof_id, eligibility in reference_consumers(output).items():
        proof = proofs.get(proof_id, {})
        uid, quote = proof.get("unit_id"), proof.get("quote", "")
        original = units.get(uid)
        exact = bool(unique_ids and original and quote.strip() and quote in original["text"])
        for sid, criterion in eligibility:
            authorized = unique_ids and uid in packets[sid]["criterion_unit_ids"][criterion]
            counts["references"] += 1
            counts["exact"] += exact
            counts["authorized"] += authorized
            counts["exact_and_authorized"] += exact and authorized
    return counts


def assess(group, output, payload, diagnostics):
    """Validate Agent assertions and compute the rubric in Python."""
    if group != payload["evidence_scope"]["branch"]:
        raise ValueError("The scorer group must match the validated payload scope")
    family = payload["job_family"]
    schema = build_format(group, family)["schema"]
    if family == "ai_engineer":
        scoring_output, repairs = repair_output(group, output, payload, schema)
    else:
        scoring_output, repairs = output, []
    assessment = _assess_response(group, scoring_output, payload, schema)
    assessment = review_assessment(guard_assessment(assessment, payload, diagnostics))
    _localize(assessment, family, group)
    valid = not assessment["validation"]["schema_errors"]
    raw_counts = _citation_counts(output, payload) if valid else None
    return assessment, {
        "raw_sha256": _rubric.sha(output),
        "scoring_copy_sha256": _rubric.sha(scoring_output),
        "repairs": repairs,
        "raw_citations": raw_counts,
        "scoring_citations": _citation_counts(scoring_output, payload) if valid and repairs else raw_counts,
    }


def verified_proofs(row):
    """Return exact proofs from credited criteria on a verified scoring row."""
    if not row.get("entry_level_score"):
        return []
    seen = set()
    proofs = []
    for audit in row["criterion_audits"]:
        if audit["status"] not in {"supported", "partial"}:
            continue
        for proof in audit["proofs"]:
            key = proof.get("unit_id"), proof.get("quote")
            if all(key) and key not in seen:
                seen.add(key)
                proofs.append(proof.copy())
    return proofs


def batch_summary(family, reports, metadata, metrics, failures, market):
    """Combine checked groups with the application's frozen all-job weights."""
    for group, assessment in reports.items():
        ids = [row["skill_id"] for row in assessment["skills"]]
        if len(ids) != len(set(ids)) or set(ids) != set(GROUP_SKILLS[family][group]):
            raise ValueError("A scored group differs from the family skill partition")
    strict_errors = {group: structural_errors(reports.get(group)) for group in GROUPS}
    failed = [group for group in GROUPS if strict_errors[group] or group in failures]
    complete = set(reports) == set(GROUPS) and not failures
    blocking = [group for group in failed if group in failures or group not in reports
                or reports[group]["citation_review"]["group_blocking_errors"]]
    usable = [group for group in GROUPS if group in reports and group not in blocking]
    scores = {row["skill_id"]: row["entry_level_score"]
              for group in usable for row in reports[group]["skills"]}
    pending = [sid for sid, score in scores.items() if score is None]
    match = coverage = None
    kind = "blocked"
    if complete and not blocking:
        demand = market["families"][family]
        n = demand["total_job_count"]
        weights = {sid: item["required_job_count"] + item["preferred_only_job_count"]
                   for sid, item in demand["skills"].items()}
        if n <= 0:
            raise ValueError("A positive all-job denominator is required")
        match = summarize_match({"skills": [
            {"resume_evidence_strength": score, "demand": {**demand["skills"][sid], "N": n}}
            for sid, score in scores.items()
        ]})
        total = sum(weights.values())
        coverage = 100 * sum(weights[sid] for sid, score in scores.items() if score is not None) / total if total else None
        kind = ("partial" if pending else "complete") if match is not None else "unscored"
    return {
        "strictly_valid": complete and not failed,
        "complete": complete,
        "failed_groups": failed,
        "group_blockers": blocking,
        "strict_errors": strict_errors,
        "operational_failures": failures,
        "groups": metrics,
        "citation_metrics": metadata,
        "scores": scores,
        "weighted_match": match,
        "score_demand_coverage": coverage,
        "pending": pending,
        "citation_pending": [sid for group in usable
                             for sid in reports[group]["citation_review"]["localized_skill_ids"]],
        "result_kind": kind,
    }
