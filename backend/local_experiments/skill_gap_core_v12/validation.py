"""Check original IDs, exact short quotes and conditional evidence fields.

These are mechanical prerequisites, not a semantic judge. A real quotation can
still describe the wrong capability or be labelled with the wrong result type.
No numerical score, keyword exception, source rewriting or model call is used.
"""
import re

from jsonschema import Draft202012Validator

from .schema import build_schema
from .sources import build_index


SCOPE = "structure_reference_and_exact_quote_integrity_not_semantic_verification"
# Leading letters/dots exclude embedded identifiers such as BM25 or v2.0.
# Attached unit suffixes are allowed (35ms, 100MB) without a domain/unit whitelist.
# This finds a literal number only; dates, ports and other values still require
# semantic interpretation by the model/reviewer rather than this checker.
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][-+]?\d+)?(?![\d.])")
_OBSERVED_TYPES = {"measured_value", "observed_state", "diagnosed_cause"}
_COMPARED_TYPES = {"relative_difference", "repeat_consistency"}


def _error(code, field, detail):
    return {"code": code, "field": field, "detail": detail}


def _pointer(parts):
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _proofs(record):
    """Yield proof objects after the fixed record shape has been checked."""
    method = record["method"]
    if method is not None:
        yield "method/proof", method["proof"]
    validation = record["validation"]
    if validation is not None:
        for key in ("check", "finding", "reference"):
            if validation[key] is not None:
                yield "validation/" + key, validation[key]


def _quote(row, quote, unit, path):
    if not quote.strip():
        row["errors"].append(_error("empty_quote", path, "Proof requires nonempty original text"))
        return
    if unit is None:
        return  # The reference error is already recorded; no fallback is possible.
    text = unit.get("text")
    if not isinstance(text, str):
        row["errors"].append(_error("invalid_source_text", path, "Original unit text must be a string"))
        return
    start = text.find(quote)
    if start < 0:
        row["errors"].append(_error(
            "quote_not_in_original", path, "Quote must be an exact contiguous substring of the referenced unit"))
        return
    row["proof_spans"].append({"field": path, "unit_id": unit["id"],
                                "start": start, "end": start + len(quote)})


def _unit(row, evidence_id, index, path, allowed_kinds, is_practice=False):
    if evidence_id not in row["evidence_ids"]:
        row["evidence_ids"].append(evidence_id)
    unit = index.get(evidence_id)
    if unit is None:
        row["errors"].append(_error("unknown_evidence_id", path, "Referenced original unit does not exist"))
        return None
    if unit.get("kind") not in allowed_kinds:
        row["errors"].append(_error("ineligible_unit_kind", path,
                                     "This structural source kind is not permitted for this field"))
    if (is_practice and row["derived_activity_id"] is not None
            and unit["activity_id"] != row["derived_activity_id"]):
        row["errors"].append(_error("cross_activity_reference", path,
                                     "Practice proof must share the original operation unit's activity"))
    return unit


def _conditional_validation(row, validation, path, index):
    kind = validation["kind"]
    finding, finding_type, reference, value = [validation[key] for key in
                                               ("finding", "finding_type", "reference", "reported_value")]
    if kind in {"check_only", "workflow_only", "unclear"}:
        if any(item is not None for item in (finding, finding_type, reference, value)):
            row["errors"].append(_error("unexpected_result_fields", path,
                                         "A non-result tier must keep finding/type/reference/value null"))
        return
    if finding is None:
        row["errors"].append(_error("missing_finding", path + "/finding", "A result tier requires its own original proof"))
    if kind == "observed":
        if finding_type not in _OBSERVED_TYPES:
            row["errors"].append(_error("invalid_finding_type", path + "/finding_type",
                                         "Observed findings require value, state or diagnosed-cause type"))
        if reference is not None:
            row["errors"].append(_error("unexpected_reference", path + "/reference",
                                         "An observed finding must keep comparison reference null"))
    elif kind == "compared":
        if finding_type not in _COMPARED_TYPES:
            row["errors"].append(_error("invalid_finding_type", path + "/finding_type",
                                         "Compared findings require relative-difference or repeated-consistency type"))
        if reference is None:
            row["errors"].append(_error("missing_comparison_reference", path + "/reference",
                                         "A compared finding requires its original comparison reference"))
    if finding_type == "measured_value":
        if value is None or not value.strip():
            row["errors"].append(_error("missing_reported_value", path + "/reported_value",
                                         "A measured-value finding needs the actual reported literal value"))
        else:
            if finding is not None and value not in finding["quote"]:
                row["errors"].append(_error("reported_value_not_in_finding", path + "/reported_value",
                                             "The reported value must occur exactly within the finding quote"))
            numeric_proof = False
            unit = index.get(finding["unit_id"]) if finding is not None else None
            original_text = unit.get("text") if unit is not None else None
            if finding is not None and value in finding["quote"] and isinstance(original_text, str):
                # Check boundaries in ORIGINAL source text, not just the model's
                # quote: a bare quote "25" cut out of "BM25" is not a number.
                original_spans = {match.span() for match in _NUMBER.finditer(original_text)}
                quote_starts = [match.start() for match in re.finditer(re.escape(finding["quote"]), original_text)]
                value_starts = [match.start() for match in re.finditer(re.escape(value), finding["quote"])]
                for quote_start in quote_starts:
                    for value_start in value_starts:
                        for match in _NUMBER.finditer(value):
                            span = (quote_start + value_start + match.start(),
                                    quote_start + value_start + match.end())
                            if span in original_spans:
                                numeric_proof = True
                                row["reported_value_spans"].append({
                                    "field": path + "/reported_value", "unit_id": unit["id"],
                                    "finding_start": quote_start,
                                    "finding_end": quote_start + len(finding["quote"]),
                                    "value_start": quote_start + value_start,
                                    "value_end": quote_start + value_start + len(value),
                                    "numeric_start": span[0], "numeric_end": span[1],
                                })
            if not numeric_proof:
                row["errors"].append(_error("reported_value_has_no_numeric_literal", path + "/reported_value",
                                             "A measured value requires an original numeric literal, not digits embedded in a model/tool identifier"))
    elif value is not None:
        row["errors"].append(_error("unexpected_reported_value", path + "/reported_value",
                                     "Only measured_value may supply reported_value; other findings use null"))


def validate_response(output, family, sources, catalog):
    """Keep valid records; mechanical failures stay pending without repair.

Only a known claim operation establishes the activity boundary. Exact quotation
and a literal number are necessary structural evidence, not proof of relevance or
an observed outcome; dates/ports/versions are not semantically classified here.
    """
    family_catalog = catalog["families"].get(family)
    if family_catalog is None:
        raise ValueError("Unknown selected job family")
    skill_ids = [skill["skill_id"] for module in family_catalog["modules"] for skill in module["skills"]]
    result = {"status": "passed", "scope": SCOPE, "global_errors": [], "unexpected_skill_ids": [], "skills": {}}
    fatal = []
    if not isinstance(output, dict) or output.get("task") != "extract_resume_evidence":
        fatal.append(_error("unexpected_task", "/task", "Expected extract_resume_evidence"))
    body = output.get("result") if isinstance(output, dict) else None
    if not isinstance(body, dict):
        fatal.append(_error("unavailable_result", "/result", "Expected a result object"))
        body = {}
    elif body.get("job_family") != family:
        fatal.append(_error("unexpected_job_family", "/result/job_family", "Result must match the selected family"))
    try:
        index = build_index(sources)
    except (ValueError, KeyError, TypeError) as error:
        index = {}
        fatal.append(_error("invalid_source_index", "/resume_sources", type(error).__name__))
    result["global_errors"].extend(fatal)
    expected = set(skill_ids)
    result["unexpected_skill_ids"] = sorted(str(key) for key in body if key != "job_family" and key not in expected)
    if result["unexpected_skill_ids"]:
        result["global_errors"].append(_error("unexpected_skill_ids", "/result",
                                               "Unrequested skills are ignored; requested valid records remain usable"))
    extra_root = sorted(str(key) for key in output if key not in {"task", "result"}) if isinstance(output, dict) else []
    if extra_root:
        result["global_errors"].append(_error("unexpected_root_fields", "/",
                                               "Unrequested root fields are ignored: " + ", ".join(extra_root)))
    schema = build_schema(catalog)["schema"]
    validator = Draft202012Validator({"$ref": "#/$defs/CoreEvidence", "$defs": schema["$defs"]})
    for skill_id in skill_ids:
        row = {"status": "passed", "errors": [], "evidence_ids": [], "derived_activity_id": None,
               "activity_derivation": None, "proof_spans": [], "reported_value_spans": []}
        result["skills"][skill_id] = row
        prefix = "/result/" + skill_id
        if fatal:
            row["errors"].append(_error("unusable_response_context", prefix,
                                         "Task, family or source integrity is not established"))
        elif skill_id not in body:
            row["errors"].append(_error("missing_skill", prefix, "Requested skill is missing"))
        else:
            record = body[skill_id]
            shape_errors = list(validator.iter_errors(record))
            if shape_errors:
                row["errors"].extend(_error("invalid_record_shape", _pointer(["result", skill_id, *error.path]),
                                             error.message[:300]) for error in shape_errors)
            elif record["kind"] == "knowledge":
                _unit(row, record["evidence_id"], index, prefix + "/evidence_id", {"claim", "listed"})
            elif record["kind"] == "uncertain":
                if record["evidence_id"] is not None:
                    _unit(row, record["evidence_id"], index, prefix + "/evidence_id", {"claim", "listed", "interest"})
                if not record["reason"].strip():
                    row["errors"].append(_error("empty_reason", prefix + "/reason", "Uncertainty needs a nonempty reason"))
            elif record["kind"] in ("practice", "limited_practice"):
                operation = index.get(record["operation_id"])
                if operation is not None and operation.get("kind") == "claim":
                    row["derived_activity_id"] = operation["activity_id"]
                    row["activity_derivation"] = "original_operation_unit_parent_not_semantic_verification"
                _unit(row, record["operation_id"], index, prefix + "/operation_id", {"claim"}, True)
                _quote(row, record["capability"]["quote"], operation, prefix + "/capability/quote")
                for field, proof in _proofs(record):
                    unit = _unit(row, proof["unit_id"], index, prefix + "/" + field + "/unit_id", {"claim"}, True)
                    _quote(row, proof["quote"], unit, prefix + "/" + field + "/quote")
                if record["validation"] is not None:
                    _conditional_validation(row, record["validation"], prefix + "/validation", index)
        if row["errors"]:
            row["status"] = "needs_confirmation"
    passed = sum(row["status"] == "passed" for row in result["skills"].values())
    result["status"] = ("failed" if passed == 0 else "partial" if passed != len(skill_ids) or result["global_errors"] else "passed")
    return result
