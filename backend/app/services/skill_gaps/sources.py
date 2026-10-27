"""Number exact résumé bullets/list entries without interpreting their meaning.

IDs are deterministic for an identical input snapshot, independent of dictionary
key order. JSON pointers retain provenance. Content bullets stay whole so that
negation, ownership and qualifications are not separated by punctuation rules.
"""
from copy import deepcopy


CLAIM_FIELDS = {"content", "description", "summary", "achievements", "responsibilities",
                "details", "highlights", "statement", "statements", "text"}
LISTED_FIELDS = {"technical_skills", "technologies", "skills"}
INTEREST_FIELDS = {"research_interests", "interests"}
CONTEXT_FIELDS = {"name", "title", "role", "company", "organization", "institution",
                  "degree", "major", "start_date", "end_date", "date", "location",
                  "url", "gpa", "authors", "venue", "proficiency", "id"}
_REMOVED = object()


def _escape(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _mode(field, inherited=None):
    key = str(field).lower().replace(" ", "_")
    if inherited in ("listed", "interest") and key in {"name", "label", "value", "text"}:
        return inherited
    if key in CLAIM_FIELDS:
        return "claim"
    if key in LISTED_FIELDS:
        return "listed"
    if key in INTEREST_FIELDS:
        return "interest"
    if key in CONTEXT_FIELDS:
        return None
    return inherited


def _path_key(path):
    return tuple((0, int(part)) if part.isdecimal() else (1, part)
                 for part in path.split("/"))


def _partition(value, path, mode, units):
    if isinstance(value, str):
        if mode is not None and value.strip():
            units.append({"path": path, "kind": mode, "text": value})
            return _REMOVED
        return value
    if isinstance(value, dict):
        context = {}
        for key in sorted(value):
            remainder = _partition(value[key], path + "/" + _escape(key), _mode(key, mode), units)
            if remainder is not _REMOVED:
                context[key] = remainder
        return context if context else _REMOVED
    if isinstance(value, list):
        context = []
        for index, item in enumerate(value):
            remainder = _partition(item, path + "/" + str(index), mode, units)
            if remainder is not _REMOVED:
                context.append({"original_index": index, "value": remainder})
        return context if context else _REMOVED
    return deepcopy(value)


def build_sources(resume):
    """Return numbered exact evidence and unnumbered metadata for each activity."""
    if not isinstance(resume, dict):
        raise TypeError("The reviewed résumé must be a JSON object")
    blocks = []
    for section in sorted(resume):
        value = resume[section]
        if section == "personal_information" or value is None or value == "" or value == [] or value == {}:
            continue
        path = "/" + _escape(section)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            blocks.extend((path + "/" + str(index), section, item) for index, item in enumerate(value))
        else:
            blocks.append((path, section, value))
    sources, evidence_number = [], 0
    for activity_number, (path, section, block) in enumerate(sorted(blocks, key=lambda item: _path_key(item[0])), 1):
        units = []
        mode = _mode(section)
        if mode is None and (isinstance(block, str) or
                             isinstance(block, list) and any(isinstance(item, str) for item in block)):
            mode = "claim"
        context = _partition(block, path, mode, units)
        numbered = []
        for unit in sorted(units, key=lambda item: _path_key(item["path"])):
            evidence_number += 1
            numbered.append({"id": f"e{evidence_number:03d}", **unit})
        if context is _REMOVED:
            context = {}
        elif not isinstance(context, dict):
            context = {"value": context}
        sources.append({"id": f"a{activity_number:03d}", "path": path,
                        "context": context, "units": numbered})
    return sources


def build_index(sources):
    """Index emitted IDs; duplicate IDs are invalid input, not semantic evidence."""
    index, activity_ids = {}, set()
    for source in sources:
        activity_id = source["id"]
        if not isinstance(activity_id, str) or not activity_id or activity_id in activity_ids:
            raise ValueError("Invalid or duplicate activity ID in input")
        activity_ids.add(activity_id)
        for unit in source["units"]:
            evidence_id = unit["id"]
            if not isinstance(evidence_id, str) or not evidence_id or evidence_id in index:
                raise ValueError("Invalid or duplicate evidence ID in input")
            index[evidence_id] = {"id": evidence_id, "path": unit["path"], "kind": unit["kind"],
                                  "text": unit["text"], "activity_id": activity_id}
    return index


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
