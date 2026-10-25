"""Separate source-exact proof spans without duplicating the family or result shapes."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
SCHEMA_NAME = "careergps_core_resume_evidence_v12"


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def choice(*values):
    return {"type": "string", "enum": list(values)}


def build_schema(catalog):
    identifier, null = {"type": "string"}, {"type": "null"}
    proof = {"$ref": "#/$defs/Proof"}
    nullable_proof = {"anyOf": [proof, null]}
    definitions = {
        "Proof": obj({"unit_id": identifier, "quote": {"type": "string", "description": "Shortest sufficient exact contiguous original fragment."}}),
        "Capability": obj({
            "relation": choice("direct_personal", "related_context", "unclear", "other_person"),
            "quote": {"type": "string", "description": "Exact core-defining mechanism within operation_id. Using/testing a component does not establish its internal algorithm or design."},
        }),
        "Method": obj({"kind": choice("named_method", "mechanism_described", "rationale_explained"), "proof": proof}),
        "Validation": obj({
            "kind": choice("check_only", "workflow_only", "unclear", "observed", "compared"),
            "check": proof,
            "finding": {**nullable_proof, "description": "A reported observation: 'checked correctness' is check-only; 'checks found no violations' supplies a finding."},
            "finding_type": {"type": ["string", "null"], "enum": ["measured_value", "observed_state", "diagnosed_cause", "relative_difference", "repeat_consistency", None]},
            "reference": nullable_proof,
            "reported_value": {"type": ["string", "null"], "description": "Exact literal numeric result within finding.quote for measured_value only; otherwise null."},
            "relation": choice("same_capability", "other_or_unclear"),
        }),
        "Absent": obj({"kind": choice("absent")}),
        "Knowledge": obj({"kind": choice("knowledge"), "evidence_id": identifier}),
        "Practice": obj({
            "kind": choice("practice", "limited_practice"), "operation_id": identifier,
            "capability": {"$ref": "#/$defs/Capability"},
            "application": choice("task_only", "concrete_action", "decision_or_tradeoff"),
            "method": {"anyOf": [{"$ref": "#/$defs/Method"}, null]},
            "validation": {"anyOf": [{"$ref": "#/$defs/Validation"}, null]},
        }),
        "Uncertain": obj({"kind": choice("uncertain"), "evidence_id": {"type": ["string", "null"]}, "reason": {"type": "string"}}),
    }
    definitions["CoreEvidence"] = {"anyOf": [{"$ref": f"#/$defs/{name}"}
                                               for name in ("Absent", "Knowledge", "Practice", "Uncertain")]}
    branches = []
    for family, data in catalog["families"].items():
        name = "".join(word.title() for word in family.split("_"))
        definitions[name] = obj({"job_family": choice(family), **{
            skill["skill_id"]: {"$ref": "#/$defs/CoreEvidence"}
            for module in data["modules"] for skill in module["skills"]}})
        branches.append({"$ref": f"#/$defs/{name}"})
    schema = obj({"task": choice("extract_resume_evidence"), "result": {"anyOf": branches}})
    schema["$defs"] = definitions
    return {"name": SCHEMA_NAME, "strict": True, "schema": schema}


if __name__ == "__main__":
    catalog = json.loads((ROOT / "core_catalog.json").read_text(encoding="utf-8"))
    (ROOT / "response-format.json").write_text(
        json.dumps(build_schema(catalog), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
