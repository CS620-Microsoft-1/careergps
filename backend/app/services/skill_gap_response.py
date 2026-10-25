"""Narrow response cleanup before the preserved v12 proof gates and arithmetic.

Discard a duplicate non-result reference, or restore uniquely located omitted
commas from the original source. No semantic evidence, tier or points are added.
"""
from copy import deepcopy

from local_experiments.skill_gap_core_v12.policy import calculate as calculate_v12
from local_experiments.skill_gap_core_v12.sources import build_index
from local_experiments.skill_gap_core_v12.validation import validate_response

RESPONSE_PROCESSING_VERSION = "v12-reference-cleanup.v2"
_NON_RESULT_TIERS = {"check_only", "workflow_only", "unclear"}


def _restorable_commas(text):
    """Only word-separating commas outside bracketed or ASCII-quoted spans."""
    result, brackets, quoted, escaped = set(), [], None, False
    pairs = {")": "(", "]": "[", "}": "{"}
    for i, char in enumerate(text):
        if quoted is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quoted:
                quoted = None
            continue
        if char in {'"', '`'} or (char == "'" and (i == 0 or not text[i - 1].isalnum())):
            quoted = char
        elif char in "([{":
            brackets.append(char)
        elif char in pairs:
            if brackets and brackets[-1] == pairs[char]:
                brackets.pop()
        elif char == "," and not brackets and i > 0 and text[i - 1].isalpha():
            following = text[i + 1:]
            if following and following[0].isspace() and following.lstrip()[:1].isalpha():
                result.add(i)
    return result


def restore_omitted_comma_quote(text, quote):
    """Find one exact original span allowing ONLY omitted prose commas.

    Matching preserves every other character, including case and whitespace.
    It never searches another source unit or guesses between repeated matches.
    Numeric separators and punctuation inside brackets/ASCII quotes are excluded.
    """
    if not isinstance(text, str) or not isinstance(quote, str) or not quote.strip() or quote in text:
        return None
    needle = quote.replace(",", "")
    if not needle.strip():
        return None
    positions = [i for i, char in enumerate(text) if char != ","]
    haystack = "".join(text[i] for i in positions)
    allowed = _restorable_commas(text)
    matches, offset = [], 0
    while (found := haystack.find(needle, offset)) >= 0:
        offset = found + 1
        start, end = positions[found], positions[found + len(needle) - 1] + 1
        consumed, skipped = 0, 0
        for i in range(start, end):
            if consumed < len(quote) and text[i] == quote[consumed]:
                consumed += 1
            elif text[i] == "," and i in allowed:
                skipped += 1
            else:
                break
        else:
            if consumed == len(quote) and skipped > 0:
                matches.append((text[start:end], {"start": start, "end": end}))
                if len(matches) > 1:
                    return None
    return matches[0] if matches else None


def _quote_targets(record, prefix):
    if record.get("kind") not in {"practice", "limited_practice"}:
        return {}
    targets = {prefix + "/capability/quote": (record["capability"], record["operation_id"])}
    if record["method"] is not None:
        proof = record["method"]["proof"]
        targets[prefix + "/method/proof/quote"] = (proof, proof["unit_id"])
    if record["validation"] is not None:
        for key in ("check", "finding", "reference"):
            proof = record["validation"][key]
            if proof is not None:
                targets[prefix + "/validation/" + key + "/quote"] = (proof, proof["unit_id"])
    return targets


def _restore_comma_quotes(family, normalized, catalog, sources):
    checks = validate_response(normalized, family, sources, catalog)
    if checks["global_errors"]:
        return []
    index = build_index(sources)
    body, proposed = normalized["result"], []
    for skill_id, check in checks["skills"].items():
        errors = check["errors"]
        if not errors or any(error["code"] != "quote_not_in_original" for error in errors):
            continue
        original = deepcopy(body[skill_id])
        targets = _quote_targets(body[skill_id], "/result/" + skill_id)
        changes = []
        for error in errors:
            target = targets.get(error["field"])
            if target is None:
                break
            proof, unit_id = target
            restored = restore_omitted_comma_quote(index[unit_id]["text"], proof["quote"])
            if restored is None:
                break
            quote, span = restored
            changes.append({"skill_id": skill_id, "field": error["field"],
                            "code": "omitted_comma_restored", "before": proof["quote"], "after": quote,
                            "source_span": {"unit_id": unit_id, **span}, "original_errors": [deepcopy(error)]})
            proof["quote"] = quote
        else:
            proposed.append((skill_id, original, changes))
            continue
        # Partial restoration must not hide another unresolved quotation.
        body[skill_id] = original
    if not proposed:
        return []
    verified = validate_response(normalized, family, sources, catalog)
    accepted = []
    for skill_id, original, changes in proposed:
        if verified["skills"][skill_id]["status"] == "passed":
            accepted.extend(changes)
        else:
            body[skill_id] = original
    return accepted


def normalize_response(family, agent_output, catalog, sources):
    """Return a separate calculation copy and an explicit field-change audit.

    Each cleanup must pass every other v12 prerequisite. Comma restoration
    additionally needs an unambiguous original span within the referenced unit.
    Other contradictory fields remain pending for review; they are not guessed.
    """
    normalized = deepcopy(agent_output)
    audit = {"version": RESPONSE_PROCESSING_VERSION,
             "scope": "duplicate_nonresult_reference_and_unique_omitted_prose_commas",
             "adjustments": [], "count": 0}
    original_checks = validate_response(agent_output, family, sources, catalog)
    body = normalized.get("result") if isinstance(normalized, dict) else None
    if not isinstance(body, dict):
        return normalized, audit
    candidates = []
    for skill_id, check in original_checks["skills"].items():
        errors = check["errors"]
        field = "/result/" + skill_id + "/validation"
        # A bad reference must not disappear just because it is redundant.
        if (len(errors) != 1 or errors[0]["code"] != "unexpected_result_fields"
                or errors[0]["field"] != field):
            continue
        record = body.get(skill_id)
        if not isinstance(record, dict) or record.get("kind") not in {"practice", "limited_practice"}:
            continue
        validation = record.get("validation")
        if (not isinstance(validation, dict) or validation.get("kind") not in _NON_RESULT_TIERS
                or any(validation.get(key) is not None for key in ("finding", "finding_type", "reported_value"))
                or validation.get("reference") is None
                or validation["reference"] != validation.get("check")):
            continue
        before = deepcopy(validation["reference"])
        validation["reference"] = None
        candidates.append({"skill_id": skill_id, "field": field + "/reference",
                           "code": "duplicate_nonresult_reference_removed",
                           "before": before, "after": None, "original_errors": deepcopy(errors)})
    if candidates:
        final_checks = validate_response(normalized, family, sources, catalog)
        for change in candidates:
            skill_id = change["skill_id"]
            if final_checks["skills"][skill_id]["status"] == "passed":
                audit["adjustments"].append(change)
            else:
                # Never use a cleanup if the original gates still reject it.
                body[skill_id] = deepcopy(agent_output["result"][skill_id])
    audit["adjustments"].extend(_restore_comma_quotes(family, normalized, catalog, sources))
    audit["count"] = len(audit["adjustments"])
    return normalized, audit


def calculate_web_report(family, agent_output, catalog, market, sources):
    normalized, audit = normalize_response(family, agent_output, catalog, sources)
    report = calculate_v12(family, normalized, catalog, market, sources)
    changed = {item["skill_id"] for item in audit["adjustments"]}
    for row in report["skills"]:
        if row["skill_id"] in changed:
            row["original_agent_assessment"] = deepcopy(agent_output["result"][row["skill_id"]])
    report["response_processing"] = audit
    return report
