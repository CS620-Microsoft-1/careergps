"""One fresh original-v2 versus entry-F3/L4/S7 three-group comparison.

Reuse the original native arm and verification from the previous comparison.
Only the entry Lifecycle payload, binding and assessment adapter are updated.
There are no Agent mutations, application changes, retries or database writes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import time

from app.core.config import SkillGapSettings
from app.services.skill_gaps import skill_group_transport as native
from app.services.skill_gaps.skill_groups import GROUPS, make_group_payloads
from experiments.entry_level_skill_gaps.entry_agents.run_experiment import invoke, read, save_new, sha, weighted_entry
from ..rules_integration import complete_contract
from ..rules_integration import experiment as common
from ..systems_fixed_fields import contract as systems_contract
from ..lifecycle_core_facts import contract as lifecycle_contract
from ..three_group_comparison import experiment as previous_runner

HERE = Path(__file__).resolve().parent
ADAPTERS = {"foundation": complete_contract, "lifecycle": lifecycle_contract, "systems": systems_contract}


def _copy_exact(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(source.read_bytes())
    if common.file_sha(source) != common.file_sha(target):
        raise ValueError("A copied artifact changed")


def prepare(args):
    root, prior, lifecycle = args.directory.resolve(), args.previous.resolve(), args.lifecycle.resolve()
    common.frozen_check(prior)
    common.frozen_check(lifecycle)
    if not read(prior / "isolation_check.json").get("all_original_and_experimental_agents_unchanged"):
        raise ValueError("The first full comparison must have a completed isolation check")
    checked = read(lifecycle / "isolation_check.json")
    if not checked.get("protected_agents_unchanged") or not checked.get("new_lifecycle_version_verified"):
        raise ValueError("The current Lifecycle version must have a completed isolation check")
    root.mkdir(parents=True, exist_ok=False)
    unchanged = {}
    for filename in ("source_input.json", "evidence_packet.json", "all_job_market.json", "catalog.json"):
        _copy_exact(prior / filename, root / filename)
        unchanged[filename] = common.file_sha(prior / filename)
        if filename != "catalog.json" and read(root / filename) != read(lifecycle / filename):
            raise ValueError("Lifecycle and the first comparison use different resume evidence or demand")
    for mode in ("original", "entry"):
        for group in GROUPS:
            relative = Path("prepared") / f"{mode}_{group}.json"
            source = lifecycle / "prepared" / "new_lifecycle.json" if mode == "entry" and group == "lifecycle" else prior / relative
            _copy_exact(source, root / relative)
            if source == prior / relative:
                unchanged[relative.as_posix()] = common.file_sha(source)
    base, packet, catalog = (read(root / f) for f in ("source_input.json", "evidence_packet.json", "catalog.json"))
    started = time.perf_counter()
    original = make_group_payloads(base)
    for group in GROUPS:
        native._load_local_contract(group)
        native._validate_scope(group, original[group], catalog)
        if original[group] != read(root / "prepared" / f"original_{group}.json"):
            raise ValueError("The original payload differs from its preserved native input")
    original_seconds = time.perf_counter() - started
    started = time.perf_counter()
    entry = {}
    for group in GROUPS:
        entry[group] = ADAPTERS[group].build_payload(original[group], packet, variant="rules")
        if entry[group] != read(root / "prepared" / f"entry_{group}.json"):
            raise ValueError("The current entry payload differs from its pinned contract")
    entry_seconds = time.perf_counter() - started
    planned = deepcopy(read(prior / "planned_bindings.json"))
    new_binding = read(lifecycle / "bindings.json")["new"]["lifecycle"]
    if new_binding["version"] != "4" or new_binding["name"] != planned["entry"]["lifecycle"]["name"]:
        raise ValueError("The current Lifecycle binding must be the same owned Agent at v4")
    planned["entry"]["lifecycle"] = new_binding
    if {g: b["version"] for g, b in planned["entry"].items()} != {"foundation": "3", "lifecycle": "4", "systems": "7"}:
        raise ValueError("The entry comparison must use versions F3/L4/S7")
    expected = read(prior / "cloud_expected.json")
    if expected != read(lifecycle / "cloud_expected.json"):
        raise ValueError("The Lifecycle trial started from a different verified cloud inventory")
    name = new_binding["name"]
    expected[name]["versions"] = ["4", "3", "2", "1"]
    expected[name]["definitions"]["4"] = sha(new_binding["definition"])
    save_new(root / "planned_bindings.json", planned)
    save_new(root / "cloud_expected.json", expected)
    plan = deepcopy(read(prior / "plan.json"))
    plan.update(experiment="entry-level-updated-three-group-comparison.v1", created_utc=common.utc(),
        previous_comparison_directory=str(prior), entry_lifecycle_directory=str(lifecycle),
        entry_versions={"foundation": "3", "lifecycle": "4", "systems": "7"},
        preparation_seconds={"original": original_seconds, "entry": entry_seconds},
        copied_unchanged_artifact_sha256=unchanged,
        entry_pipeline="Foundation v3 complete rules, Lifecycle v4 core facts and Systems v7 instructions with unchanged v6 fixed-field scoring; identical all-job weighting.")
    plan["payload_sha256"]["entry"]["lifecycle"] = sha(entry["lifecycle"])
    plan["source_counts"]["entry"]["lifecycle"] = previous_runner._source_counts(entry["lifecycle"])
    save_new(root / "plan.json", plan)
    frozen = read(prior / "frozen_files.json")
    frozen.update(read(lifecycle / "frozen_files.json"))
    paths = [p for source in (prior, lifecycle) for p in source.rglob("*.json") if p.is_file()]
    paths += [p for p in root.rglob("*.json") if p.is_file()]
    paths += [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += [p for p in previous_runner.HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    frozen.update({str(p.resolve()): common.file_sha(p) for p in paths})
    save_new(root / "frozen_files.json", frozen)
    print(json.dumps({"prepared": True, "planned_scoring_calls": 6, "entry_versions": plan["entry_versions"],
                      "all_job_count": plan["all_job_family_count"], "unchanged_copied_artifacts": len(unchanged)}), flush=True)


def _run_entry(root, endpoint):
    plan, bindings = read(root / "plan.json"), read(root / "bindings.json")
    folder = root / "runs" / "entry"
    folder.mkdir(parents=True, exist_ok=False)
    common.frozen_check(root)
    started = time.perf_counter()
    payloads = {g: read(root / "prepared" / f"entry_{g}.json") for g in GROUPS}
    if any(sha(p) != plan["payload_sha256"]["entry"][g] for g, p in payloads.items()):
        raise ValueError("A frozen entry payload changed")
    base, market = read(root / "source_input.json"), read(root / "all_job_market.json")
    outputs, metrics, failures = {}, {}, {}
    call_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(invoke, payloads[g], bindings["entry"][g], folder / g, endpoint, group=g): g for g in GROUPS}
        for future in as_completed(futures):
            group = futures[future]
            try:
                outputs[group], metrics[group] = future.result()
            except Exception as error:
                failures[group] = {"type": type(error).__name__, "phase": "model_call", "automatic_retry": False}
    parallel_wall = time.perf_counter() - call_started
    score_started, report = time.perf_counter(), None
    if not failures:
        try:
            rows = []
            for group in GROUPS:
                assessment = ADAPTERS[group].assess_output(outputs[group], payloads[group])
                save_new(folder / group / "assessment.json", assessment)
                rows.extend(assessment["skills"])
            if len(rows) != len(base["core_skills"]) or {r["skill_id"] for r in rows} != {r["skill_id"] for r in base["core_skills"]}:
                raise ValueError("Entry scores do not cover the exact original 23-skill scope")
            report = weighted_entry(rows, market, plan["family"])
            if report["demand_snapshot_fingerprint"] != market["source_fingerprint"]:
                raise ValueError("Entry scoring changed the all-job demand snapshot")
            save_new(folder / "report.json", report)
        except Exception as error:
            failures["local_processing"] = {"type": type(error).__name__, "phase": "local_scoring", "automatic_retry": False}
            save_new(folder / "processing_failure.json", failures["local_processing"])
            report = None
    score_seconds, wall = time.perf_counter() - score_started, time.perf_counter() - started
    prep = plan["preparation_seconds"]["entry"]
    summary = {"mode": "entry", "wall_seconds": wall, "preparation_seconds": prep,
        "preflight_seconds": 0.0, "total_measured_seconds": prep + wall,
        "parallel_call_wall_seconds": parallel_wall, "local_assessment_seconds": score_seconds,
        "groups": metrics, "failed_groups": failures, "complete": not failures,
        "scoring_calls_attempted": 3, "match": report["match"] if report else None,
        "pending": report["unscored_skill_ids"] if report else None, "fresh_conversations": True,
        "scored_skill_count": sum(r["resume_evidence_strength"] is not None for r in report["skills"]) if report else None,
        **common.frozen_check(root)}
    save_new(folder / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("mode", "wall_seconds", "total_measured_seconds", "match", "pending", "failed_groups")}), flush=True)
    return summary


def run(args):
    root = previous_runner._require_live(args)
    if (root / "runs").exists() or (root / "run_setup.json").exists():
        raise ValueError("The one-pair comparison cannot be repeated or resumed automatically")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    endpoint, planned = common.endpoint_from_file(args.env_file), read(root / "planned_bindings.json")
    expected = read(root / "cloud_expected.json")
    setup_started = time.perf_counter()
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as client:
            observed = common.snapshot_agents(client, expected)
    if observed != expected:
        raise ValueError("A protected Agent inventory changed before the comparison")
    save_new(root / "cloud_before.json", observed)
    inventory_seconds = time.perf_counter() - setup_started
    values = {"skill_gap_foundry_project_endpoint": endpoint}
    for group in GROUPS:
        values[f"skill_gap_{group}_agent_name"] = planned["original"][group]["name"]
        values[f"skill_gap_{group}_agent_version"] = "2"
    preflight_started = time.perf_counter()
    prepared = native.preflight(GROUPS,
        lambda g, filename, value: previous_runner._save_event(root / "preflight" / g, filename, value),
        settings=SkillGapSettings(_env_file=None, **values))
    preflight_seconds = time.perf_counter() - preflight_started
    bindings = {"entry": planned["entry"], "original": {}}
    for group, item in prepared.items():
        if item.agent_name != planned["original"][group]["name"] or item.agent_version != "2" or sha(item.definition) != expected[item.agent_name]["definitions"]["2"]:
            raise ValueError("Native preflight resolved a different original Agent snapshot")
        bindings["original"][group] = {"name": item.agent_name, "version": item.agent_version, "definition": item.definition}
    save_new(root / "bindings.json", bindings)
    save_new(root / "run_setup.json", {"cloud_inventory_seconds": inventory_seconds,
        "native_preflight_seconds": preflight_seconds, "total_setup_seconds": time.perf_counter() - setup_started,
        "preflight_before_all_inference": True, "model_calls": 0})
    original = previous_runner._run_arm(root, "original", endpoint, prepared, preflight_seconds)
    entry = _run_entry(root, endpoint)
    save_new(root / "comparison_run.json", {"scoring_calls_attempted": 6,
        "complete": original["complete"] and entry["complete"], "arms": {"original": original, "entry": entry},
        "rounds_per_arm": 1, "additional_model_calls": 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--lifecycle", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare" and (args.previous is None or args.lifecycle is None):
        parser.error("prepare requires --previous and --lifecycle")
    {"prepare": prepare, "run": run, "verify": previous_runner.verify}[args.action](args)


if __name__ == "__main__":
    main()
