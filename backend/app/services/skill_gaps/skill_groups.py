"""Disjoint core-skill assignments with complete, unchanged résumé sources.

The three internal contracts reuse the existing v12 evidence record definitions.
Each skill has one owner; this module only validates and assembles whole records
for the unchanged public v12 report calculator. It does not calculate scores,
invent evidence, or treat an unassigned skill as absent.
"""
from copy import deepcopy

from .response import normalize_response
from .schema import build_schema
from .sources import build_index
from .validation import validate_response


GROUPS = ("foundation", "lifecycle", "systems")
BRANCHES = GROUPS
PARTITION_POLICY_VERSION = "core-skill-partitions.v1"
SELECTION_POLICY_VERSION = "sole-owner-whole-record-assembly.v1"

# These are work assignments, not evidence eligibility or scoring mappings.
# Original catalog order, definitions and exclusions remain authoritative.
GROUP_SKILLS = {
    "ai_engineer": {
        "foundation": (
            "general_programming", "python", "software_engineering", "sql",
            "math_statistics", "data_preparation", "data_pipelines", "feature_engineering",
        ),
        "lifecycle": (
            "machine_learning", "deep_learning", "model_training", "fine_tuning",
            "model_evaluation", "experimentation", "model_deployment", "mlops",
        ),
        "systems": (
            "ai_infrastructure", "generative_ai", "llm", "rag", "ai_agents",
            "prompt_engineering", "vector_retrieval",
        ),
    },
    "software_engineer": {
        "foundation": (
            "programming", "algorithms", "object_oriented_design", "ai_assisted_development",
            "relational_sql", "nosql_search", "version_control",
        ),
        "lifecycle": (
            "system_design", "backend_apis", "frontend", "code_quality", "testing",
            "debugging", "code_review",
        ),
        "systems": (
            "distributed_systems", "cloud", "containers", "delivery_automation",
            "performance", "observability_operations", "reliability", "security",
        ),
    },
    "data_analyst": {
        "foundation": (
            "sql", "analytical_scripting", "spreadsheets", "statistics",
            "data_analysis", "business_analytics",
        ),
        "lifecycle": (
            "requirements_analysis", "experimentation", "causal_inference",
            "data_pipelines", "data_modeling", "data_quality",
        ),
        "systems": (
            "dashboarding", "data_visualization", "bi_tools", "warehousing",
            "large_scale_processing", "workflow_automation",
        ),
    },
}


def absent_output(payload: dict) -> dict:
    """A complete absence response for the known-empty assigned input scope."""
    skills = [skill["skill_id"] for skill in payload["core_skills"]]
    if len(skills) != len(set(skills)):
        raise ValueError("Core skill IDs must be unique")
    return {"task": "extract_resume_evidence", "result": {
        "job_family": payload["job_family"], **{skill: {"kind": "absent"} for skill in skills},
    }}


def _group(group: str) -> str:
    if group not in GROUPS:
        raise ValueError("Choose foundation, lifecycle or systems skill groups")
    return group


def _skills(catalog: dict, family: str) -> list[dict]:
    if family not in GROUP_SKILLS:
        raise ValueError("The selected family has no approved skill-group assignment")
    try:
        skills = [skill for module in catalog["families"][family]["modules"]
                  for skill in module["skills"]]
        ids = [skill["skill_id"] for skill in skills]
    except (KeyError, TypeError) as error:
        raise ValueError("The skill catalog is unavailable or malformed") from error
    assigned = [skill for group in GROUPS for skill in GROUP_SKILLS[family][group]]
    if (len(ids) != len(set(ids)) or len(assigned) != len(set(assigned))
            or set(ids) != set(assigned)):
        raise ValueError("Skill groups must cover the selected catalog exactly once")
    return skills


def group_catalog(catalog: dict, group: str) -> dict:
    """Return lossless selected-group cards for every supplied supported family.

    Reject catalog drift instead of silently dropping a new or renamed skill.
    The public catalog and Schema remain untouched.
    """
    _group(group)
    result = deepcopy(catalog)
    for family in catalog["families"]:
        _skills(catalog, family)
        assigned = set(GROUP_SKILLS[family][group])
        modules = []
        for module in result["families"][family]["modules"]:
            module["skills"] = [skill for skill in module["skills"] if skill["skill_id"] in assigned]
            if module["skills"]:
                modules.append(module)
        result["families"][family]["modules"] = modules
    return result


def build_group_format(catalog: dict, group: str) -> dict:
    """Build a strict internal Schema with only the group's required core keys."""
    result = build_schema(group_catalog(catalog, group))
    result["name"] = f"careergps_core_group_{group}_v12"
    return result


def _source_scope(sources: list[dict]) -> list[str]:
    if not isinstance(sources, list):
        raise ValueError("Resume sources must be an ordered list")
    try:
        build_index(sources)
        for source in sources:
            if not isinstance(source["path"], str) or not source["path"].startswith("/"):
                raise ValueError("Every activity needs its original JSON path")
        return [source["id"] for source in sources]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Resume sources must retain unique original activity and unit IDs") from error


def make_group_payloads(payload: dict) -> dict[str, dict]:
    """Partition only core cards; every group receives all original source units."""
    family = payload["job_family"]
    if family not in GROUP_SKILLS:
        raise ValueError("The selected family has no approved skill-group assignment")
    ids = [card["skill_id"] for card in payload["core_skills"]]
    assigned = [skill for group in GROUPS for skill in GROUP_SKILLS[family][group]]
    if len(ids) != len(set(ids)) or set(ids) != set(assigned):
        raise ValueError("Input core cards must match the complete skill-group assignment")
    activities = _source_scope(payload["resume_sources"])
    result = {}
    for group in GROUPS:
        item = deepcopy(payload)
        owned = set(GROUP_SKILLS[family][group])
        item["core_skills"] = [card for card in item["core_skills"] if card["skill_id"] in owned]
        item["evidence_scope"] = {
            "branch": group,
            "partition_policy_version": PARTITION_POLICY_VERSION,
            "activity_ids": list(activities),
            "assigned_skill_ids": [card["skill_id"] for card in item["core_skills"]],
        }
        result[group] = item
    return result


def process_group_output(output: dict, payload: dict, catalog: dict) -> tuple[dict, dict, dict]:
    """Apply the original cleanup and proof gates only to assigned skill records."""
    scope = payload.get("evidence_scope")
    if not isinstance(scope, dict):
        raise ValueError("A skill-group input requires its explicit assignment scope")
    group = _group(scope.get("branch"))
    family = payload["job_family"]
    expected = [skill["skill_id"] for skill in _skills(catalog, family)
                if skill["skill_id"] in GROUP_SKILLS[family][group]]
    actual = [card["skill_id"] for card in payload["core_skills"]]
    if (actual != expected or scope.get("assigned_skill_ids") != expected
            or scope.get("partition_policy_version") != PARTITION_POLICY_VERSION
            or scope.get("activity_ids") != _source_scope(payload["resume_sources"])):
        raise ValueError("The skill-group assignment does not match its supplied catalog and sources")
    scoped_catalog = group_catalog(catalog, group)
    normalized, processing = normalize_response(
        family, output, scoped_catalog, payload["resume_sources"])
    checks = validate_response(normalized, family, payload["resume_sources"], scoped_catalog)
    return normalized, processing, checks


def validate_group_output(output: dict, payload: dict, catalog: dict) -> dict:
    return process_group_output(output, payload, catalog)[2]


def merge_group_outputs(family: str, outputs: dict, catalog: dict,
                        sources: list[dict]) -> tuple[dict, dict]:
    """Assemble each sole owner's whole record into the unchanged public v12.

    Missing or mechanically invalid assigned evidence stays pending. An extra
    unassigned key invalidates that owner's group, never another group. No other
    Agent's record can replace an owner's uncertainty, failure or omission.
    """
    if not isinstance(outputs, dict) or set(outputs) != set(GROUPS):
        raise ValueError("Outputs for foundation, lifecycle and systems are all required")
    cards = _skills(catalog, family)
    payloads = make_group_payloads({"task": "extract_resume_evidence", "job_family": family,
        "core_skills": cards, "resume_sources": sources})
    audit = {
        "partition_policy_version": PARTITION_POLICY_VERSION,
        "selection_policy_version": SELECTION_POLICY_VERSION,
        "scope": "sole_owner_validated_whole_record_assembly_not_semantic_or_numeric_evidence_repair",
        "uncertainty_policy": "only_the_assigned_owner_controls_each_skill_no_cross_group_fallback",
        "branches": {}, "skills": {},
    }
    normalized, checks = {}, {}
    owners = {skill: group for group in GROUPS for skill in GROUP_SKILLS[family][group]}
    for group in GROUPS:
        normalized[group], processing, checks[group] = process_group_output(outputs[group], payloads[group], catalog)
        audit["branches"][group] = {
            "activity_ids": payloads[group]["evidence_scope"]["activity_ids"],
            "assigned_skill_ids": payloads[group]["evidence_scope"]["assigned_skill_ids"],
            "response_processing": processing, "validation": checks[group],
        }
    merged = {"task": "extract_resume_evidence", "result": {"job_family": family}}
    for skill in cards:
        skill_id = skill["skill_id"]
        owner = owners[skill_id]
        check = checks[owner]["skills"][skill_id]
        body = normalized[owner].get("result") if isinstance(normalized[owner], dict) else None
        record = body.get(skill_id) if isinstance(body, dict) else None
        blockers = []
        if checks[owner]["global_errors"] or check["status"] != "passed":
            blockers.append({"branch": owner, "reason": "invalid_group_evidence",
                "errors": deepcopy([*checks[owner]["global_errors"], *check["errors"]])})
        elif (record["kind"] in {"practice", "limited_practice"}
                and record["capability"]["relation"] != "direct_personal"):
            blockers.append({"branch": owner, "reason": "non_direct_personal_capability"})
        if blockers:
            merged["result"][skill_id] = {"kind": "uncertain", "evidence_id": None,
                "reason": "Assigned skill-group evidence requires review; " +
                          "; ".join(f"{item['branch']}: {item['reason']}" for item in blockers)}
            audit["skills"][skill_id] = {"state": "uncertain", "reason": "assigned_owner_requires_review",
                "selected_branch": owner, "blockers": blockers}
        else:
            merged["result"][skill_id] = deepcopy(record)
            kind = record["kind"]
            audit["skills"][skill_id] = {
                "state": "uncertain" if kind == "uncertain" else "absent" if kind == "absent" else "selected",
                "reason": "sole_assigned_owner_whole_record", "selected_branch": owner,
                "selected_kind": kind, "blockers": [],
            }
    return merged, audit
