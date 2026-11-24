"""Portable three-skill diagnostic contract; structural checks are not semantics."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from app.services.skill_gaps.scoring_math import grade

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[2]
ENTRY = ROOT.with_name("entry_agents")
SKILLS = ("python", "llm", "ai_agents")
STATUSES = ("supported", "partial", "not_evidenced", "uncertain")
WEIGHTS = (Decimal(".5"), Decimal(".3"), Decimal(".2"))
POINTS = {"supported": Decimal(1), "partial": Decimal(".5"), "not_evidenced": Decimal(0)}
MODES = ("control", "rules_v1", "rules_v1_1")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def output_format():
    criterion = _object({
        "status": {"type": "string", "enum": list(STATUSES)},
        "basis": {"type": "string", "enum": ["practice", "unclear", "none"]},
        "unit_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
    })
    row = _object({
        "case_id": {"type": "string"},
        "skill_id": {"type": "string", "enum": list(SKILLS)},
        "criteria": _object({cid: deepcopy(criterion) for cid in ("c1", "c2", "c3")}),
    })
    return {"type": "json_schema", "name": "entry_rule_calibration_pilot_v1", "strict": True,
            "schema": _object({"task": {"type": "string", "enum": ["assess_rule_cases"]},
                                "results": {"type": "array", "items": row}})}


def load_cases(version="v1.1"):
    if version not in ("v1", "v1.1"):
        raise ValueError("Unknown rule case version")
    cases = read(ROOT / "cases.json")
    return [case for case in cases if version == "v1.1" or case["introduced_in"] == "v1"]


def build_payload(cases, catalog=None, criteria=None):
    """Whitelist source fields, replacing all caller IDs with opaque batch IDs.

    Expected labels, rationales, split, introduced_in and descriptive case names
    stay outside the model request. Each independent case retains its own full
    activity. No real applicant input is included in the repository.
    """
    if catalog is None:
        catalog = read(BACKEND / "app/services/skill_gaps/data/core_catalog.json")
    if criteria is None:
        criteria = read(ENTRY / "criteria.json")
    cards = {s["skill_id"]: s for m in catalog["families"]["ai_engineer"]["modules"] for s in m["skills"]}
    criteria = criteria["families"]["ai_engineer"]
    for skill in SKILLS:
        selected = criteria[skill]["criteria"]
        if ([row["id"] for row in selected] != ["c1", "c2", "c3"]
                or tuple(Decimal(str(row["weight"])) for row in selected) != WEIGHTS
                or any(row["minimum_evidence"] != "practice" for row in selected)):
            raise ValueError("The rule pilot requires the frozen three practical criteria")
    forwarded = []
    for number, case in enumerate(cases, 1):
        if case["skill_id"] not in SKILLS:
            raise ValueError("Unsupported rule-pilot skill")
        if "activity" in case:
            activity = deepcopy(case["activity"])
        else:
            activity = {"id": f"a{number:03}", "context": {}, "units": [
                {"id": u["unit_id"], "kind": u["kind"], "text": u["text"]} for u in case["units"]]}
        units = activity["units"]
        ids = [u["id"] for u in units]
        if (not units or any(not isinstance(uid, str) or not uid for uid in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("Each independent case needs unique nonempty unit IDs")
        anchors = deepcopy(case.get("anchor_unit_ids", [ids[0]]))
        if not anchors or len(anchors) != len(set(anchors)) or not set(anchors) <= set(ids):
            raise ValueError("Anchors must be unique IDs within the case activity")
        for unit in units:
            if unit["kind"] not in ("claim", "listed", "interest") or not isinstance(unit["text"], str):
                raise ValueError("Case source kind and text must be explicit")
        forwarded.append({"case_id": f"c{number:03}", "skill_id": case["skill_id"],
                          "activity": activity, "anchor_unit_ids": anchors})
    return {"task": "assess_rule_cases", "job_family": "ai_engineer",
            "core_skills": {s: cards[s] for s in SKILLS},
            "entry_level_criteria": {s: criteria[s] for s in SKILLS}, "cases": forwarded}


def assess_output(output, payload, mode="rules_v1_1"):
    """Score without rewriting any labels or inventing semantic verification."""
    if mode not in MODES:
        raise ValueError("Unknown scoring mode")
    schema_errors = [{"path": list(e.path), "error": e.validator}
                     for e in Draft202012Validator(output_format()["schema"]).iter_errors(output)]
    observed = output.get("results", []) if isinstance(output, dict) else []
    if not isinstance(observed, list):
        observed = []
    expected = payload["cases"]
    observed_scope = [(r.get("case_id"), r.get("skill_id")) if isinstance(r, dict) else None for r in observed]
    expected_scope = [(c["case_id"], c["skill_id"]) for c in expected]
    global_error = bool(schema_errors) or observed_scope != expected_scope
    by_id = {r["case_id"]: r for r in observed if isinstance(r, dict) and isinstance(r.get("case_id"), str)}
    rows = []
    for case in expected:
        record = by_id.get(case["case_id"], {}).get("criteria", {})
        if not isinstance(record, dict):
            record = {}
        index = {u["id"]: u for u in case["activity"]["units"]}
        errors = ["schema_or_case_scope_error"] if global_error else []
        statuses, values, refs, original_units, policy_violations = [], [], {}, {}, []
        core_item = record.get("c1", {})
        core_status = core_item.get("status") if isinstance(core_item, dict) else None
        for cid in ("c1", "c2", "c3"):
            item = record.get(cid, {})
            item = item if isinstance(item, dict) else {}
            status, basis, ids = item.get("status"), item.get("basis"), item.get("unit_ids", [])
            statuses.append(status)
            values.append(POINTS.get(status) if isinstance(status, str) else None)
            refs[cid] = deepcopy(ids)
            if (not isinstance(status, str) or status not in STATUSES or not isinstance(ids, list)
                    or any(not isinstance(uid, str) for uid in ids)):
                errors.append(cid + ":invalid_criterion")
                continue
            if len(ids) != len(set(ids)) or any(uid not in index for uid in ids):
                errors.append(cid + ":invalid_source_ids")
            if status in ("supported", "partial"):
                if basis != "practice" or not ids or any(index.get(uid, {}).get("kind") != "claim" for uid in ids):
                    errors.append(cid + ":ineligible_practice_reference")
            if status == "not_evidenced" and (ids or basis != "none"):
                errors.append(cid + ":absence_must_have_no_references")
            if status == "uncertain":
                errors.append(cid + ":uncertain")
                if basis != "unclear":
                    errors.append(cid + ":uncertain_basis")
            if cid == "c1" and status in ("supported", "partial", "uncertain") and not set(ids).intersection(case["anchor_unit_ids"]):
                errors.append(cid + ":missing_anchor")
            if cid != "c1" and status in ("supported", "partial") and core_status not in ("supported", "partial"):
                errors.append(cid + ":positive_detail_without_core")
            original_units[cid] = [index[uid] for uid in ids if uid in index]
            if mode != "control" and cid in ("c1", "c2") and status == "partial":
                policy_violations.append(cid + ":partial_disabled")
            if mode != "control" and cid != "c1" and core_status in ("not_evidenced", "uncertain") and status != "not_evidenced":
                policy_violations.append(cid + ":detail_not_suppressed_for_unestablished_core")
        errors += policy_violations
        score = None if errors or any(v is None for v in values) else sum(w * v for w, v in zip(WEIGHTS, values))
        if score is not None and statuses[0] != "supported":
            score = min(score, Decimal(".6"))
        gap = None if score is None else Decimal(1) - score
        rows.append({"case_id": case["case_id"], "skill_id": case["skill_id"], "statuses": statuses,
                     "score": None if score is None else float(score), "grade": grade(gap),
                     "state": "pending" if score is None else "scored", "errors": errors,
                     "policy_violations": policy_violations, "unit_ids": refs, "original_units": original_units})
    return {"rows": rows, "schema_errors": schema_errors, "semantic_entailment_validated": False,
            "quote_copying": "Original units attached by local lookup; valid IDs do not prove semantic support."}


def score_response(output, payload):
    """Adapter for the shared runner; explicit-rule v1 and v1.1 share scoring."""
    return assess_output(output, payload, "rules_v1_1")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Build a label-free request from synthetic cases")
    prepare.add_argument("--version", choices=("v1", "v1.1"), default="v1.1")
    prepare.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("score", help="Check a saved response offline")
    score.add_argument("--input", type=Path, required=True)
    score.add_argument("--response", type=Path, required=True)
    score.add_argument("--mode", choices=MODES, default="rules_v1_1")
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        save_new(args.output, build_payload(load_cases(args.version)))
    else:
        save_new(args.output, assess_output(read(args.response), read(args.input), args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
