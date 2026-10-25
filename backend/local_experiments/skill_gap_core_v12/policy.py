"""Source-exact proof gates around the unchanged core evidence arithmetic."""
import json
from pathlib import Path
from ..skill_gap_core_v9.policy import calculate as _calculate
from .sources import build_index, attach_source_index
from .validation import validate_response
from .coverage import audit_coverage

POLICY = json.loads(Path(__file__).with_name("scoring_policy.json").read_text(encoding="utf-8"))
POLICY_VERSION = POLICY["policy_version"]
RELATIONS = {"direct_personal": "direct_personal_operation", "related_context": "related_context",
             "unclear": "unclear_ownership", "other_person": "other_person"}


def resolve_record(raw, index):
    """Translate already-checked proofs into the original scorer's input shape."""
    kind = raw["kind"]
    if kind == "absent":
        return {"kind": kind}
    if kind == "knowledge":
        unit = index[raw["evidence_id"]]
        return {"kind": kind, "source_id": unit["activity_id"], "anchor": unit["text"]}
    if kind == "uncertain":
        unit = index.get(raw["evidence_id"])
        return {"kind": kind, "source_id": unit["activity_id"] if unit else None, "reason": raw["reason"]}
    operation = index[raw["operation_id"]]
    resolved = {"kind": kind, "source_id": operation["activity_id"],
                "target_anchor": raw["capability"]["quote"], "operation_anchor": operation["text"],
                "eligibility": RELATIONS[raw["capability"]["relation"]], "application": raw["application"],
                "method": None, "validation": None}
    if raw["method"] is not None:
        resolved["method"] = {"kind": raw["method"]["kind"], "anchor": raw["method"]["proof"]["quote"]}
    if raw["validation"] is not None:
        item = raw["validation"]
        validation = {"kind": item["kind"], "relation": item["relation"], "check_anchor": item["check"]["quote"]}
        if item["finding"] is not None:
            validation.update(finding_anchor=item["finding"]["quote"], finding_type=item["finding_type"])
        if item["reference"] is not None:
            validation["reference_anchor"] = item["reference"]["quote"]
        resolved["validation"] = validation
    return resolved


def calculate(family, agent_output, catalog, market, sources):
    checks = validate_response(agent_output, family, sources, catalog)
    try:
        index, source_integrity_ok = build_index(sources), True
    except (TypeError, ValueError, KeyError):
        index, source_integrity_ok = {}, False
    body = agent_output.get("result") if isinstance(agent_output, dict) else None
    body = body if isinstance(body, dict) else {}
    resolved = {key: (resolve_record(body[key], index) if check["status"] == "passed" else
                      {"kind": "uncertain", "source_id": None, "reason": "Local reference/proof check failed"})
                for key, check in checks["skills"].items()}
    report = _calculate(family, {"result": {"job_family": family, **resolved}}, catalog, market)
    for row in report["skills"]:
        row["agent_assessment"] = body.get(row["skill_id"])
        row["local_reference_check"] = checks["skills"][row["skill_id"]]
        row["evidence_verification"] = "source_exact_proof_integrity_not_semantic_truth"
    report.update(policy_version=POLICY_VERSION, reference_validation=checks,
                  evidence_coverage=audit_coverage(agent_output, checks, sources),
                  mechanical_integrity_checked=True, exact_quotes_checked=True,
                  semantic_evidence_verified=False, agent_output_verified=False,
                  base_numeric_rubric="core-evidence-gap.v5")
    report["limitations"] = [
        "Operation-bound capability text and cited proof spans are checked against original units, not judged semantically.",
        "A literal reported number is a necessary reference prerequisite, not proof that the number is an actual measurement result.",
        "Related/unclear capability and invalid references/proofs remain pending, without automatic fallback, repair or score downgrade.",
        "Potential same-operation method/check references are review candidates only; they never fill fields or change scores.",
        "All original points, caps, grade thresholds and demand are unchanged and not empirically calibrated.",
        "A indicates a smaller resume evidence gap; F means no positive selected evidence, not inability.",
    ]
    if source_integrity_ok:
        attach_source_index(report, sources)
    else:
        report.update(source_index={}, unresolved_display_sources=[], source_lookup_scope="unusable_input_source_index_not_resolved")
    return report
