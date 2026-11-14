"""Preserve strict validation while isolating recoverable skill review."""
from copy import deepcopy

from app.services.skill_gaps.skill_groups import GROUP_SKILLS
from app.services.skill_gaps.sources import build_index


CRITERIA = {"c1", "c2", "c3"}
CRITERION_CITATION_ERRORS = {"quote_not_exact", "proof_outside_fixed_criterion_candidates"}
FACT_CITATION_ERRORS = {"quote_not_exact", "fact_proof_outside_fixed_criterion_candidates"}
EXPECTED_PENDING_ERRORS = {"criterion_uncertain", "blocked_by_unresolved_core", "children_blocked_by_unresolved_core"}
INCOMPLETE_SEARCH = "candidate_selection_incomplete"
CROSS_ACTIVITY = "cross_activity_practice_evidence"
PRACTICE_LINKAGE = "same_personal_example"
CREDITED = {"supported", "partial"}


def _credited_activity_ids(row, assessment, source_index):
    sid = row["skill_id"]
    credited = {
        item["criterion_id"]: item
        for item in row["criterion_audits"] if item["status"] in CREDITED
    }
    proofs = [proof for item in credited.values() for proof in item["proofs"]]
    fact = assessment.get("fact_audits", {}).get(sid)
    fact_criterion = "c3" if sid == "llm" else "c1"
    if fact and fact_criterion in credited and fact["mapped_status"] in CREDITED:
        proofs.extend(fact["proofs"])
    if row.get("partial_core_applied") and "c1" in credited:
        proofs.extend(assessment["partial_core_audits"][sid]["proofs"])
    # The prepared source index is authoritative even when the scoring audit
    # omits activity_id. Validated proofs always identify a supplied source.
    return sorted({source_index[proof["unit_id"]]["activity_id"] for proof in proofs})


def guard_assessment(assessment, payload, selection_diagnostics):
    """Keep strict Agent scoring audits and abstain on unsupported conclusions.

    A scored result from one activity still relies on the existing rubric's
    semantic workload check within that activity. Distinct activity IDs
    are conservatively treated as distinct here. For incomplete searches,
    excluding an inspected candidate cannot exclude a different unseen one.
    """
    result = deepcopy(assessment)
    packets = payload["fixed_evidence_packets"]["skills"]
    diagnostics = selection_diagnostics["skills"]
    source_index = build_index(payload["resume_sources"])
    reasons = {}
    for row in result["skills"]:
        sid = row["skill_id"]
        search_incomplete = diagnostics[sid]["search_incomplete"]
        if type(search_incomplete) is not bool:
            raise ValueError(f"Expected Boolean search completeness for {sid}")
        score = row["entry_level_score"]
        if score is None or row.get("errors"):
            continue
        activities = []
        if score == 0 and search_incomplete:
            reason = INCOMPLETE_SEARCH
        elif score > 0 and packets[sid]["linkage_policy"] == PRACTICE_LINKAGE:
            activities = _credited_activity_ids(row, result, source_index)
            if len(activities) <= 1:
                continue
            reason = CROSS_ACTIVITY
        else:
            continue
        row["selection_review"] = {
            "reason": reason,
            "original_entry_level_score": score,
            "original_entry_level_gap": row["entry_level_gap"],
            "original_entry_level_grade": row["entry_level_grade"],
            "original_calculation_state": row["calculation_state"],
            "credited_activity_ids": activities,
        }
        row.update(entry_level_score=None, entry_level_gap=None, entry_level_grade=None,
                   calculation_state="needs_confirmation")
        reasons[sid] = reason
    result["candidate_selection_review"] = {"affected_skill_ids": list(reasons), "reasons": reasons}
    result["unscored_skill_ids"] = [
        row["skill_id"] for row in result["skills"] if row["entry_level_score"] is None
    ]
    return result


def structural_errors(assessment):
    if not isinstance(assessment, dict):
        return ["missing_assessment"]
    validation = assessment.get("validation", {})
    errors = [f"schema:{x}" for x in validation.get("schema_errors", [])]
    errors += list(validation.get("global_errors", []))
    errors += list(assessment.get("raw_child_validation_errors", []))
    for row in assessment.get("skills", []):
        for issue in row.get("errors", []):
            if issue.split(":")[-1] not in EXPECTED_PENDING_ERRORS:
                errors.append(f"{row.get('skill_id')}:{issue}")
    for sid, audit in assessment.get("fact_audits", {}).items():
        errors += [f"{sid}:fact:{x}" for x in audit.get("errors", [])]
    return list(dict.fromkeys(errors))


def _local_skill(issue, skill_ids):
    parts = issue.split(":")
    if len(parts) != 3:
        return None
    skill, scope, code = parts
    if skill not in skill_ids:
        return None
    if scope in CRITERIA and code in CRITERION_CITATION_ERRORS:
        return skill
    if scope == "fact" and (code in FACT_CITATION_ERRORS
                            or (skill == "llm" and code == "unidentified_output_requires_empty_detail")):
        return skill
    return None


def review_assessment(assessment):
    """Retain strict errors and abstain on independently attributable citation failures.

    Group blockers include schema, source integrity, and any errors outside the
    narrow citation allowlist. Consumers must check the blockers before using a
    group's rows for a partial report.
    """
    result = deepcopy(assessment)
    rows = result["skills"]
    skill_ids = {row["skill_id"] for row in rows}
    local, blockers = {}, []
    for issue in structural_errors(result):
        skill = _local_skill(issue, skill_ids)
        if skill is None:
            blockers.append(issue)
        else:
            local.setdefault(skill, []).append(issue)

    result["citation_review"] = {
        "localized_skill_ids": [row["skill_id"] for row in rows if row["skill_id"] in local],
        "localized_errors_by_skill": local,
        "group_blocking_errors": blockers,
    }
    if local and not blockers:
        for row in rows:
            if row["skill_id"] in local:
                row.update(entry_level_score=None, entry_level_gap=None, entry_level_grade=None,
                           calculation_state="needs_confirmation")
        result["unscored_skill_ids"] = [row["skill_id"] for row in rows if row["entry_level_score"] is None]
    return result


def _affected_skill(issue, assigned):
    parts = issue.split(":")
    if len(parts) != 3:
        return None
    skill, field, error = parts
    if skill not in assigned:
        return None
    if field in CRITERIA and error == "unknown_proof_id":
        return skill
    if (skill, field, error) == ("llm", "fact", "claimed_check_event_without_proof"):
        return skill
    return None


def _localize(assessment, family, group):
    review = assessment["citation_review"]
    blocking = review["group_blocking_errors"]
    if not blocking:
        return
    rows = assessment["skills"]
    assigned = set(GROUP_SKILLS[family][group])
    ids = [row["skill_id"] for row in rows]
    if (assessment["job_family"], assessment["branch"]) != (family, group):
        return
    if len(ids) != len(assigned) or set(ids) != assigned:
        return

    # The original scorer already checks the response schema, source integrity,
    # criterion permissions and proof pool. Keep blocking the group if any
    # remaining strict error cannot be attributed to a supported citation use.
    consumers = [_affected_skill(issue, assigned) for issue in blocking]
    if None in consumers:
        return
    local = review["localized_errors_by_skill"]
    for skill, issue in zip(consumers, blocking):
        local.setdefault(skill, []).append(issue)
    review["group_blocking_errors"] = []
    review["localized_skill_ids"] = [sid for sid in ids if sid in local]
    for row in rows:
        if row["skill_id"] in local:
            row.update(entry_level_score=None, entry_level_gap=None,
                       entry_level_grade=None, calculation_state="needs_confirmation")
    assessment["unscored_skill_ids"] = [
        row["skill_id"] for row in rows if row["entry_level_score"] is None
    ]
