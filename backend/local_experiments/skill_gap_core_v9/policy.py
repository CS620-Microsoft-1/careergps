"""Fixed arithmetic for independent method and check/finding fields.

Only categorical inputs and field availability are considered here. There is no
source/quote/ID lookup, semantic verifier, content-specific override or repair.
"""
import json
from pathlib import Path
from ..skill_gap_core_v5.policy import assess_strength as _assess, calculate as _calculate, grade

POLICY = json.loads(Path(__file__).with_name("scoring_policy.json").read_text(encoding="utf-8"))
POLICY_VERSION = POLICY["policy_version"]
VALIDATION_LEVELS = {"check_only": "method_only", "workflow_only": "none", "unclear": "none",
                     "observed": "method_and_result", "compared": "comparative_or_repeated"}
FINDING_TYPES = {"observed": {"measured_value", "observed_state", "diagnosed_cause"},
                 "compared": {"relative_difference", "repeat_consistency"}}


def selection_points():
    return {
        "application_points": {k: v for k, v in POLICY["application_points"].items() if k != "listed"},
        "method_points": POLICY["method_points"],
        "validation_points_if_same_capability": {k: POLICY["validation_points"][v] for k, v in VALIDATION_LEVELS.items()},
        "denominator": POLICY["points_denominator"], "knowledge_score": POLICY["listed_score"],
        "task_only_cap": POLICY["task_only_cap"], "limited_practice_cap": POLICY["partial_cap"],
    }


def present(value):
    return isinstance(value, str) and bool(value.strip())


def method_level(raw):
    if "method" not in raw:
        return None
    method = raw["method"]
    if method is None:
        return "none"
    if not isinstance(method, dict):
        return None
    kind = method.get("kind")
    if not isinstance(kind, str) or kind not in POLICY["method_points"] or kind == "none":
        return None
    return kind if present(method.get("anchor")) else None


def validation_level(raw):
    if "validation" not in raw:
        return None, {"validation_points_withheld": False}
    validation = raw["validation"]
    if validation is None:
        return "none", {"validation_points_withheld": False}
    if not isinstance(validation, dict):
        return None, {"validation_points_withheld": False}
    relation, tag = validation.get("relation"), validation.get("kind")
    audit = {"validation_relation": relation, "reported_validation_kind": tag,
             "validation_points_withheld": False}
    if not isinstance(tag, str) or tag not in VALIDATION_LEVELS:
        return None, audit
    complete = present(validation.get("check_anchor"))
    if tag in FINDING_TYPES:
        finding_type = validation.get("finding_type")
        complete = complete and present(validation.get("finding_anchor"))
        complete = complete and isinstance(finding_type, str) and finding_type in FINDING_TYPES[tag]
        if tag == "compared":
            complete = complete and present(validation.get("reference_anchor"))
        audit["finding_fields_available"] = complete
    if not complete:
        return None, audit
    if relation == "other_or_unclear":
        audit["validation_points_withheld"] = True
        return "none", audit
    if relation != "same_capability":
        return None, audit
    audit["validation_points_withheld"] = tag in ("workflow_only", "unclear")
    return VALIDATION_LEVELS[tag], audit


def scoring_input(raw):
    if not isinstance(raw, dict):
        return raw, {"reason": "unavailable_evidence"}
    kind = raw.get("kind")
    if kind == "absent":
        return {"status": "not_evidenced", "evidence": []}, {"reason": "explicit_absence"}
    if kind == "knowledge":
        return {"status": "supported", "evidence": [{"support_relation": "direct", "attribution": "self",
                                                     "application_detail": "listed"}]}, {"reason": "selected_explicit_knowledge"}
    if kind not in ("practice", "limited_practice"):
        return {"status": "needs_confirmation"}, {"reason": "unknown_or_uncertain_evidence"}
    if raw.get("eligibility") != "direct_personal_operation":
        return {"status": "needs_confirmation"}, {"reason": "practice_eligibility_not_established"}
    if not present(raw.get("target_anchor")) or not present(raw.get("operation_anchor")):
        return {"status": "needs_confirmation"}, {"reason": "target_or_operation_unavailable"}
    method = method_level(raw)
    validation, audit = validation_level(raw)
    audit.update(reason="selected_grounded_practice", effective_method_level=method,
                 effective_validation_level=validation,
                 grounding_check="field_presence_only_not_source_or_semantic_verification")
    evidence = {"support_relation": "direct", "attribution": "self", "application_detail": raw.get("application"),
                "method_detail": method, "validation_level": validation}
    return {"status": "partial" if kind == "limited_practice" else "supported", "evidence": [evidence]}, audit


def assess_strength(raw):
    normalized, audit = scoring_input(raw)
    return {**_assess(normalized), "grounding_and_result_gate": audit,
            "selected_source_id": raw.get("source_id") if isinstance(raw, dict) else None}


def evidence_strength(raw):
    return assess_strength(raw)["score"]


def calculate(family, agent_output, catalog, market):
    body = agent_output.get("result") if isinstance(agent_output, dict) else None
    skills = {k: v for k, v in body.items() if k != "job_family"} if isinstance(body, dict) else {}
    report = _calculate(family, {"result": {"skills": {k: scoring_input(v)[0] for k, v in skills.items()}}}, catalog, market)
    for row in report["skills"]:
        raw = skills.get(row["skill_id"])
        row["agent_assessment"] = raw
        row["scoring_breakdown"] = assess_strength(raw)
    report.update(policy_version=POLICY_VERSION, base_numeric_rubric="core-evidence-gap.v5")
    report["limitations"] = [
        "Method and check/finding fragments are model selections, not locally verified facts.",
        "Field-availability scoring does not establish quote accuracy, semantic relevance or causal links.",
        "One selected reference per core is retained; stronger evidence may still be missed.",
        "Source lookup is display-only; no repair call or keyword-dependent score override is used.",
        "Numeric points, caps and grade thresholds are unchanged and remain uncalibrated product rules.",
        "C spans evidence strength .40 to below .60; numeric differences may share the same grade.",
        "A indicates a smaller resume evidence gap; F means no positive selected evidence, not inability.",
    ]
    return report
