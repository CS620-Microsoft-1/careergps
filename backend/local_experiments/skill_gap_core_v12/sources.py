"""Preserve v10 original units; display only source text behind selected proofs."""
from copy import deepcopy
from ..skill_gap_core_v10.sources import build_sources, build_index


def references(record):
    if not isinstance(record, dict):
        return []
    refs = [record.get("evidence_id"), record.get("operation_id")]
    method = record.get("method")
    if isinstance(method, dict) and isinstance(method.get("proof"), dict):
        refs.append(method["proof"].get("unit_id"))
    validation = record.get("validation")
    if isinstance(validation, dict):
        for name in ("check", "finding", "reference"):
            proof = validation.get(name)
            if isinstance(proof, dict):
                refs.append(proof.get("unit_id"))
    return [value for value in refs if isinstance(value, str)]


def attach_source_index(report, sources):
    index = build_index(sources)
    activities = {source["id"]: source for source in sources}
    used = {value for row in report["skills"] for value in references(row.get("agent_assessment"))}
    report["source_index"] = {
        key: {**index[key], "activity_path": activities[index[key]["activity_id"]]["path"],
              "activity_context": deepcopy(activities[index[key]["activity_id"]]["context"])}
        for key in sorted(used) if key in index}
    report["unresolved_display_sources"] = sorted(used-index.keys())
    report["source_lookup_scope"] = "original_unit_display_with_checked_model_span_references_not_semantic_truth"
    return report
