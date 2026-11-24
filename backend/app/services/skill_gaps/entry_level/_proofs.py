"""Validate exact proof aliases and conservative quote restoration."""

from collections import Counter, defaultdict
from copy import deepcopy
import re

from jsonschema import Draft202012Validator

from app.services.skill_gaps.response import restore_omitted_comma_quote
from app.services.skill_gaps.sources import build_index


PROOF_FIELDS = {"proof_id", "unit_id", "quote"}


def _rewrite_list(refs, aliases):
    canonical = [aliases.get(pid, pid) for pid in refs]
    # Keep a repeated input ID visible to the strict scorer. Only distinct
    # aliases of the same original span may collapse to one reference.
    return list(dict.fromkeys(canonical)) if len(refs) == len(set(refs)) else canonical


def _rewrite_references(record, aliases):
    if isinstance(record, dict):
        for key, value in record.items():
            if key == "proof_ids":
                record[key] = _rewrite_list(value, aliases)
            else:
                _rewrite_references(value, aliases)
    elif isinstance(record, list):
        for item in record:
            _rewrite_references(item, aliases)


def normalize_output(output, payload, schema, *, partial_core):
    """Return an independent scoring copy and aliases for exact, valid duplicates."""
    proofs = output.get("proofs") if isinstance(output, dict) else None
    if not isinstance(proofs, list) or len(proofs) < 2:
        return output, {}
    if any(
        not isinstance(proof, dict) or set(proof) != PROOF_FIELDS
        or not all(isinstance(proof[field], str) for field in PROOF_FIELDS)
        for proof in proofs
    ):
        return output, {}
    counts = Counter(proof["proof_id"] for proof in proofs)
    if any(count != 1 or not re.fullmatch(r"p[1-9][0-9]*", pid) for pid, count in counts.items()):
        return output, {}
    spans, aliases = {}, {}
    for proof in proofs:
        key = (proof["unit_id"], proof["quote"])
        pid = proof["proof_id"]
        first = spans.setdefault(key, pid)
        if first != pid:
            aliases[pid] = first
    if not aliases:
        return output, {}

    if not Draft202012Validator(schema).is_valid(output):
        return output, {}
    index = build_index(payload["resume_sources"])
    if any(not quote.strip() or uid not in index or quote not in index[uid]["text"] for uid, quote in spans):
        return output, {}

    normalized = deepcopy(output)
    normalized["proofs"] = [proof for proof in normalized["proofs"] if proof["proof_id"] not in aliases]
    _rewrite_references(normalized["result"], aliases)
    if partial_core:
        normalized["partial_core"] = {
            sid: _rewrite_list(refs, aliases) if refs is not None else None
            for sid, refs in normalized["partial_core"].items()
        }
    return normalized, aliases


def reference_consumers(output):
    """Index proof IDs by skill and criterion in a schema-validated response."""
    consumers = defaultdict(set)

    def register(refs, skill_id, criterion_id):
        for proof_id in refs or ():
            consumers[proof_id].add((skill_id, criterion_id))

    for skill_id, record in output["result"].items():
        if skill_id == "job_family":
            continue
        for criterion in record.get("criteria", ()):
            register(criterion["proof_ids"], skill_id, criterion["criterion_id"])
        if "core_facts" in record:
            register(record["core_facts"]["proof_ids"], skill_id, "c1")
        if "check_facts" in record:
            register(record["check_facts"]["proof_ids"], skill_id, "c3")
        for criterion_id, child in (record.get("children") or {}).items():
            register(child["proof_ids"], skill_id, criterion_id)
    for skill_id, refs in output.get("partial_core", {}).items():
        register(refs, skill_id, "c1")
    return dict(consumers)


def repair_output(group, output, payload, schema):
    """Return a scoring copy and audit when omitted prose commas can be restored.

    The same original unit must remain permitted in every consuming criterion.
    Proof IDs, permissions, classification fields and exact LLM fact spans are
    left as emitted. Existing scoring must still validate the restored response.
    """
    if group != payload["evidence_scope"]["branch"]:
        raise ValueError("The repair group must match its input scope")
    if not Draft202012Validator(schema).is_valid(output):
        return output, []

    proof_ids = [proof["proof_id"] for proof in output["proofs"]]
    if len(set(proof_ids)) != len(proof_ids) or any(
        not re.fullmatch(r"p[1-9][0-9]*", proof_id) for proof_id in proof_ids
    ):
        return output, []

    consumers = reference_consumers(output)
    units = build_index(payload["resume_sources"])
    packets = payload["fixed_evidence_packets"]["skills"]
    original_spans = Counter((proof["unit_id"], proof["quote"]) for proof in output["proofs"])
    reserved_spans = set(original_spans)
    replacements, repairs = {}, []
    for proof in output["proofs"]:
        proof_id, unit_id, quote = proof["proof_id"], proof["unit_id"], proof["quote"]
        uses = sorted(consumers.get(proof_id, ()))
        if not uses or unit_id not in units or any(
            unit_id not in packets.get(sid, {}).get("criterion_unit_ids", {}).get(cid, ())
            for sid, cid in uses
        ):
            continue
        # Preserve an existing duplicate diagnostic and avoid creating one.
        if original_spans[unit_id, quote] > 1:
            continue
        restored = restore_omitted_comma_quote(units[unit_id]["text"], quote)
        if restored is None:
            continue
        exact, source_range = restored
        if (unit_id, exact) in reserved_spans:
            continue
        reserved_spans.add((unit_id, exact))
        replacements[proof_id] = exact
        repairs.append({
            "proof_id": proof_id,
            "unit_id": unit_id,
            "reason": "omitted_prose_comma",
            **source_range,
            "references": [
                {"skill_id": sid, "criterion_id": cid} for sid, cid in uses
            ],
        })

    if not replacements:
        return output, []
    repaired = deepcopy(output)
    for proof in repaired["proofs"]:
        if proof["proof_id"] in replacements:
            proof["quote"] = replacements[proof["proof_id"]]
    return repaired, repairs
