"""Recalculate a completed saved response offline, without replacing its run.

Only local JSON and versioned assets are read. This module does not import the
Agent transport, queue, account service, or database configuration.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.response import calculate_web_report


_METRICS = ("resume_evidence_strength", "skill_gap", "skill_gap_grade", "priority", "calculation_state")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(directory: Path) -> dict[str, str]:
    return {path.name: digest(path) for path in sorted(directory.iterdir()) if path.is_file()}


def save(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def assessment(row: dict) -> dict:
    check = row.get("local_reference_check", {})
    return {**{key: row[key] for key in _METRICS},
            "reference_status": check.get("status"),
            "reference_errors": [error["code"] for error in check.get("errors", [])]}


def summary(report: dict) -> dict:
    scored = [row for row in report["skills"] if row["resume_evidence_strength"] is not None]
    return {"skill_count": len(report["skills"]), "scored": len(scored),
            "pending": [row["skill_id"] for row in report["skills"] if row["resume_evidence_strength"] is None],
            "grades": dict(Counter(row["skill_gap_grade"] for row in scored))}


def replay(run_directory: Path, output_directory: Path) -> dict:
    """Write a separate audit and report; never update cached runs or call a model."""
    run_directory, output_directory = run_directory.resolve(), output_directory.resolve()
    if not run_directory.is_dir():
        raise ValueError("The saved run directory does not exist.")
    if output_directory == run_directory or run_directory in output_directory.parents:
        raise ValueError("Replay output must be outside the saved run directory.")
    if output_directory.exists():
        raise ValueError("Replay output must be a new directory; existing files are never overwritten.")
    original_hashes = source_hashes(run_directory)
    payload, agent_output, before = [load(run_directory / name) for name in
        ("input.json", "agent.response.json", "skill_gaps.json")]
    state = load(run_directory / "status.json") if (run_directory / "status.json").is_file() else {}
    if state and state.get("status") != "completed":
        raise ValueError("Only completed saved runs can be replayed.")
    family = payload["job_family"]
    if payload.get("task") != "extract_resume_evidence" or before["job_family"] != family:
        raise ValueError("The saved input and report must describe the same evidence task and job family.")
    catalog, market = [load(ASSET_ROOT / name) for name in ("core_catalog.json", "market_snapshot.json")]
    old_rows = {row["skill_id"]: row for row in before["skills"]}
    expected_ids = {skill["skill_id"] for module in catalog["families"][family]["modules"] for skill in module["skills"]}
    if len(old_rows) != len(before["skills"]) or set(old_rows) != expected_ids:
        raise ValueError("The saved report's skill IDs must match the current catalog.")
    current_market = market["families"][family]
    for skill_id, row in old_rows.items():
        demand = {**current_market["skills"][skill_id], "N": current_market["total_job_count"]}
        if row["demand"] != demand:
            raise ValueError("Demand changed since the saved run; this reference-only replay is refused.")
    started = time.perf_counter()
    after = calculate_web_report(family, agent_output, catalog, market, payload["resume_sources"])
    elapsed = round(time.perf_counter() - started, 6)
    if after["policy_version"] != before["policy_version"]:
        raise ValueError("The scoring policy version changed; this reference-only replay is refused.")
    for key in ("user_id", "resume_id", "database_used"):
        if key in before:
            after[key] = before[key]
    new_rows = {row["skill_id"]: row for row in after["skills"]}
    adjustments = after["response_processing"]["adjustments"]
    comparisons = [{"skill_id": skill_id, "skill_name": old["skill_name"],
        "before": assessment(old), "after": assessment(new_rows[skill_id]),
        "changed": assessment(old) != assessment(new_rows[skill_id]),
        "alignment_codes": [item["code"] for item in adjustments if item["skill_id"] == skill_id]}
        for skill_id, old in old_rows.items()]
    scored_before = [row for row in comparisons if row["before"]["resume_evidence_strength"] is not None]
    result = {"mode": "offline_saved_response_replay", "created_at": datetime.now(timezone.utc).isoformat(),
        "original_run_id": state.get("id", run_directory.name), "job_family": family,
        "original_model_calls": state.get("model_calls"), "new_model_calls": 0,
        "original_run_elapsed_seconds": state.get("elapsed_seconds"), "offline_calculation_seconds": elapsed,
        "before": summary(before), "after": summary(after),
        "changed_skill_ids": [row["skill_id"] for row in comparisons if row["changed"]],
        "unchanged_previously_scored_skill_ids": [row["skill_id"] for row in scored_before
            if all(row["before"][key] == row["after"][key] for key in _METRICS)],
        "changed_previously_scored_skill_ids": [row["skill_id"] for row in scored_before
            if any(row["before"][key] != row["after"][key] for key in _METRICS)],
        "response_processing_version": after["response_processing"]["version"],
        "source_file_hashes_before": original_hashes,
        "asset_hashes": {name: digest(ASSET_ROOT / name) for name in
            ("core_catalog.json", "market_snapshot.json", "scoring_policy.json", "response-format.json")},
        "processing_code_sha256": {name: digest(ASSET_ROOT.parent / name) for name in
            ("response.py", "reference_alignment.py", "scoring.py", "evidence_scoring.py",
             "scoring_math.py", "validation.py", "sources.py")},
        "skills": comparisons}
    if source_hashes(run_directory) != original_hashes:
        raise RuntimeError("The source run changed during replay; no replay output was written.")
    output_directory.mkdir(parents=True, exist_ok=False)
    save(output_directory / "skill_gaps.before.json", before)
    save(output_directory / "skill_gaps.after.json", after)
    save(output_directory / "response_processing.json", after["response_processing"])
    save(output_directory / "local_checks.json", after["reference_validation"])
    result["source_file_hashes_after"] = source_hashes(run_directory)
    result["source_files_unchanged"] = result["source_file_hashes_after"] == original_hashes
    save(output_directory / "comparison.json", result)
    table = ["# Offline Skill Gap reference-alignment comparison", "",
        f"Family: `{family}`. New model calls: **0**. Original model calls: {result['original_model_calls']}.",
        f"Original run: {result['original_run_elapsed_seconds']} seconds. Offline calculation: {elapsed} seconds.", "",
        f"Scored skills: **{result['before']['scored']} -> {result['after']['scored']}**.",
        f"Pending skills: **{len(result['before']['pending'])} -> {len(result['after']['pending'])}**.", "",
        "| Core skill | Evidence strength before | After | Gap grade before | After | Reference check after |",
        "| --- | ---: | ---: | --- | --- | --- |"]
    for row in comparisons:
        if row["changed"]:
            old, new = row["before"], row["after"]
            values = [row["skill_name"], old["resume_evidence_strength"], new["resume_evidence_strength"],
                      old["skill_gap_grade"], new["skill_gap_grade"], new["reference_status"]]
            table.append("| " + " | ".join("Pending" if value is None else str(value) for value in values) + " |")
    table.extend(["", "Unchanged scored skills retain their previous numbers; the original run and raw response remain intact.",
        "This is a separate offline result. It does not replace the web cache or start a new analysis.",
        "A passed quotation check establishes source integrity, not semantic relevance or demonstrated ability.",
        "Alignment does not add missing methods, modify Agent categories, or change demand/scoring rules.", ""])
    (output_directory / "README.md").write_text("\n".join(table), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.run_dir, args.output)
    print(json.dumps({key: result[key] for key in ("job_family", "new_model_calls",
        "offline_calculation_seconds", "before", "after", "changed_skill_ids", "source_files_unchanged")}))


if __name__ == "__main__":
    main()
