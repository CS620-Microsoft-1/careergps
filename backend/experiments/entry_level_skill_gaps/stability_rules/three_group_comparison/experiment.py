"""One isolated six-call comparison of original and current entry Agents.

Original groups use native preflight, transport, merging and web-report scoring.
Entry groups retain their existing experimental contracts and all-job weighting.
There are no Agent mutations, application routing changes, retries or database
operations. The two arms deliberately retain their different evidence scopes.
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
from app.services.skill_gaps.match import summarize_match
from app.services.skill_gaps.response import calculate_web_report
from app.services.skill_gaps.skill_groups import GROUPS, make_group_payloads, merge_group_outputs
from experiments.entry_level_skill_gaps.entry_agents.run_experiment import invoke, read, save_new, sha, weighted_entry
from ..rules_integration import complete_contract
from ..rules_integration import experiment as common
from ..systems_fixed_fields import contract as systems_contract

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
MODES = ("original", "entry")


def _source_counts(payload):
    return {"activities": len(payload["resume_sources"]),
            "units": sum(len(s["units"]) for s in payload["resume_sources"]),
            "assigned_skills": len(payload["evidence_scope"]["assigned_skill_ids"])}


def prepare(args):
    root, system_root, other_root = args.directory.resolve(), args.entry_systems.resolve(), args.entry_others.resolve()
    common.frozen_check(system_root)
    common.frozen_check(other_root)
    for previous in (system_root, other_root):
        check = read(previous / "isolation_check.json")
        if not check.get("protected_agents_unchanged") or not check.get("application_files_unchanged"):
            raise ValueError("Previously verified isolated Agent bindings are required")
    root.mkdir(parents=True, exist_ok=False)
    base, packet, market = (read(system_root / f) for f in ("source_input.json", "evidence_packet.json", "all_job_market.json"))
    for filename, value in (("source_input.json", base), ("evidence_packet.json", packet), ("all_job_market.json", market)):
        if value != read(other_root / filename):
            raise ValueError("The two existing entry experiments do not share the same frozen source and demand")
        save_new(root / filename, value)
    catalog = read(BACKEND / "app/services/skill_gaps/data/core_catalog.json")
    save_new(root / "catalog.json", catalog)
    family = base["job_family"]
    if family != "ai_engineer":
        raise ValueError("This one-pair comparison is scoped to the existing AI Engineer resume")
    start = time.perf_counter()
    original = make_group_payloads(base)
    for group in GROUPS:
        native._load_local_contract(group)
        native._validate_scope(group, original[group], catalog)
    original_seconds = time.perf_counter() - start
    start = time.perf_counter()
    entry = {}
    for group in GROUPS:
        adapter = systems_contract if group == "systems" else complete_contract
        entry[group] = adapter.build_payload(original[group], packet, variant="rules")
        previous_payload = (system_root / "prepared" / "new_systems.json" if group == "systems"
                            else other_root / "prepared" / f"rules_{group}.json")
        if entry[group] != read(previous_payload):
            raise ValueError("Current entry payload differs from its existing pinned experiment")
    entry_seconds = time.perf_counter() - start
    bindings = read(system_root / "bindings.json")["new"]
    other_bindings = read(other_root / "bindings.json")["rules"]
    expected_versions = {"foundation": "3", "lifecycle": "3", "systems": "7"}
    for group in GROUPS:
        if bindings[group]["version"] != expected_versions[group]:
            raise ValueError("The requested current entry versions must be 3, 3 and 7")
        if group != "systems" and bindings[group] != other_bindings[group]:
            raise ValueError("Foundation or Lifecycle differs from the preserved complete-rule Agent")
    before = read(system_root / "cloud_before.json")
    expected_cloud = {**deepcopy(before["protected"]), **deepcopy(before["owned"])}
    systems_name = bindings["systems"]["name"]
    expected_cloud[systems_name]["versions"] = ["7", "6", "5", "4", "3", "2", "1"]
    expected_cloud[systems_name]["definitions"]["7"] = sha(bindings["systems"]["definition"])
    original_bindings = {g: {"name": f"skill-gap-{g}", "version": "2"} for g in GROUPS}
    for binding in original_bindings.values():
        if "2" not in expected_cloud[binding["name"]]["definitions"]:
            raise ValueError("The approved original v2 binding is absent from the protected inventory")
    save_new(root / "planned_bindings.json", {"original": original_bindings, "entry": bindings})
    save_new(root / "cloud_expected.json", expected_cloud)
    payloads = {"original": original, "entry": entry}
    for mode, groups in payloads.items():
        for group, payload in groups.items():
            save_new(root / "prepared" / f"{mode}_{group}.json", payload)
    plan = {"experiment": "entry-level-original-three-group-comparison.v1", "created_utc": common.utc(),
        "family": family, "entry_systems_directory": str(system_root), "entry_others_directory": str(other_root),
        "schedule": list(MODES), "rounds_per_arm": 1, "planned_scoring_calls": 6,
        "original_versions": {g: "2" for g in GROUPS}, "entry_versions": expected_versions,
        "source_sha256": sha(base), "source_units_sha256": sha(base["resume_sources"]),
        "packet_sha256": sha(packet), "market_sha256": sha(market),
        "all_job_family_count": market["families"][family]["total_job_count"],
        "all_job_snapshot_fingerprint": market["source_fingerprint"],
        "preparation_seconds": {"original": original_seconds, "entry": entry_seconds},
        "payload_sha256": {m: {g: sha(p) for g, p in groups.items()} for m, groups in payloads.items()},
        "source_counts": {m: {g: _source_counts(p) for g, p in groups.items()} for m, groups in payloads.items()},
        "protected_agent_names": sorted(expected_cloud), "agent_mutations": 0,
        "original_pipeline": "Native approved v2 group preflight and invoke_prepared, merge_group_outputs, calculate_web_report and summarize_match.",
        "entry_pipeline": "Foundation/Lifecycle v3 complete rules and Systems v7 instructions with unchanged v6 fixed-field scoring; weighted_entry uses identical all-job demand.",
        "comparison_scope": "Same confirmed resume and job demand, but original groups receive every source unit and select evidence freely; entry groups retain reviewer-fixed criterion evidence. Scoring rubrics also differ.",
        "timing_scope": "Arm wall time covers payload loading, three parallel calls and native local validation/scoring. Preparation and original preflight are separate. total_measured_seconds sums these phases, not resume parsing or prior reviewer evidence selection. Shared cloud inventory checks are excluded from arm timing.",
        "transport_scope": "Both transports create fresh conversations. Original binding checks occur in native preflight; entry invoke verifies pinned definitions within each measured call.",
        "automatic_retries": 0, "result_cache_used": False, "additional_repair_logic": False,
        "original_normalization": "Retain existing native bounded quote/reference normalization and its full processing audits.",
        "database_access": False, "runtime_integration": False,
        "stopping_rule": "Validate all original and entry bindings before any inference. Execute one original arm and one entry arm only. Retain failures without retry; no aggregate comparison is valid if an arm fails.",
        "limitations": ["One pair cannot establish stability, accuracy or a general speedup.",
                        "Original and entry scores measure different evidence rubrics and are not calibrated hiring probabilities."]}
    save_new(root / "plan.json", plan)
    frozen = read(system_root / "frozen_files.json")
    frozen.update(read(other_root / "frozen_files.json"))
    paths = [p for prior in (system_root, other_root) for p in prior.rglob("*.json") if p.is_file()]
    paths += [p for p in root.rglob("*.json") if p.is_file()]
    paths += [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += [p for p in (BACKEND / "app/services/skill_gaps").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += [p for p in (BACKEND / "app/prompts/skill_gaps/skill_groups").rglob("*") if p.is_file()]
    frozen.update({str(p.resolve()): common.file_sha(p) for p in paths})
    save_new(root / "frozen_files.json", frozen)
    print(json.dumps({"prepared": True, "planned_scoring_calls": 6, "all_job_count": plan["all_job_family_count"],
                      "original_units_per_group": [x["units"] for x in plan["source_counts"]["original"].values()]}), flush=True)


def _require_live(args):
    if not args.live or not args.env_file:
        raise ValueError("Live read/call operations require --live and --env-file")
    root = args.directory.resolve()
    common.frozen_check(root)
    return root


def _save_event(folder, filename, value):
    path, ordinal = folder / filename, 1
    while path.exists():
        ordinal += 1
        path = folder / f"{Path(filename).stem}.{ordinal:02}{Path(filename).suffix}"
    save_new(path, value)


def _original_call(prepared, payload, folder):
    folder.mkdir(parents=True, exist_ok=False)
    save_new(folder / "input.json", payload)
    save_new(folder / "agent_binding.json", {"name": prepared.agent_name, "version": prepared.agent_version,
                                             "definition_sha256": sha(prepared.definition)})
    timings, requests = {}, [0]
    started = time.perf_counter()
    try:
        def on_request():
            requests[0] += 1
        output = native.invoke_prepared(prepared, payload, lambda name, value: save_new(folder / name, value),
                                        on_request, timings)
        save_new(folder / "agent.response.json", output)
        return output
    except Exception as error:
        save_new(folder / "failure.json", {"type": type(error).__name__, "automatic_retry": False,
                                           "model_requests": requests[0]})
        raise
    finally:
        timings["group_wall_seconds"] = time.perf_counter() - started
        raw = read(folder / "agent.raw.json") if (folder / "agent.raw.json").is_file() else {}
        save_new(folder / "metrics.json", {"group": prepared.branch, "name": prepared.agent_name,
            "version": prepared.agent_version, "timings": timings, "usage": raw.get("usage"),
            "model_requests": requests[0], "transport": "native_invoke_prepared"})


def _assemble_original(outputs, base, catalog, market):
    merged, audit = merge_group_outputs(base["job_family"], outputs, catalog, base["resume_sources"])
    report = calculate_web_report(base["job_family"], merged, catalog, market, base["resume_sources"])
    report["match"] = summarize_match(report)
    return report, merged, audit


def _run_arm(root, mode, endpoint, original_prepared, preflight_seconds):
    plan, bindings = read(root / "plan.json"), read(root / "bindings.json")
    folder = root / "runs" / mode
    folder.mkdir(parents=True, exist_ok=False)
    common.frozen_check(root)
    started = time.perf_counter()
    payloads = {g: read(root / "prepared" / f"{mode}_{g}.json") for g in GROUPS}
    if any(sha(p) != plan["payload_sha256"][mode][g] for g, p in payloads.items()):
        raise ValueError("A frozen arm payload changed")
    base, market, catalog = read(root / "source_input.json"), read(root / "all_job_market.json"), read(root / "catalog.json")
    outputs, metrics, failures = {}, {}, {}
    call_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_original_call, original_prepared[g], payloads[g], folder / g) if mode == "original"
                   else pool.submit(invoke, payloads[g], bindings["entry"][g], folder / g, endpoint, group=g): g for g in GROUPS}
        for future in as_completed(futures):
            group = futures[future]
            try:
                if mode == "original":
                    outputs[group] = future.result()
                else:
                    outputs[group], metrics[group] = future.result()
            except Exception as error:
                failures[group] = {"type": type(error).__name__, "phase": "model_call", "automatic_retry": False}
            if (folder / group / "metrics.json").is_file():
                metrics[group] = read(folder / group / "metrics.json")
    parallel_wall = time.perf_counter() - call_started
    score_started = time.perf_counter()
    report = None
    if not failures:
        try:
            if mode == "original":
                report, merged, audit = _assemble_original(outputs, base, catalog, market)
                save_new(folder / "merged.response.json", merged)
                save_new(folder / "extraction_audit.json", audit)
                save_new(folder / "response_processing.json", report["response_processing"])
                save_new(folder / "coverage_audit.json", report["evidence_coverage"])
                for group in GROUPS:
                    ids = set(payloads[group]["evidence_scope"]["assigned_skill_ids"])
                    save_new(folder / group / "assessment.json", {"branch": group, **audit["branches"][group],
                        "skills": [r for r in report["skills"] if r["skill_id"] in ids]})
            else:
                rows = []
                for group in GROUPS:
                    adapter = systems_contract if group == "systems" else complete_contract
                    assessed = adapter.assess_output(outputs[group], payloads[group])
                    save_new(folder / group / "assessment.json", assessed)
                    rows.extend(assessed["skills"])
                if len(rows) != len(base["core_skills"]) or {r["skill_id"] for r in rows} != {r["skill_id"] for r in base["core_skills"]}:
                    raise ValueError("Entry group scores do not cover the exact original skill scope")
                report = weighted_entry(rows, market, plan["family"])
            if report["demand_snapshot_fingerprint"] != market["source_fingerprint"]:
                raise ValueError("An arm report changed the all-job demand snapshot")
            save_new(folder / "report.json", report)
        except Exception as error:
            failures["local_processing"] = {"type": type(error).__name__, "phase": "local_scoring", "automatic_retry": False}
            save_new(folder / "processing_failure.json", failures["local_processing"])
            report = None
    score_seconds = time.perf_counter() - score_started
    wall = time.perf_counter() - started
    prep = plan["preparation_seconds"][mode]
    preflight = preflight_seconds if mode == "original" else 0.0
    summary = {"mode": mode, "wall_seconds": wall, "preparation_seconds": prep,
        "preflight_seconds": preflight, "total_measured_seconds": prep + preflight + wall,
        "parallel_call_wall_seconds": parallel_wall, "local_assessment_seconds": score_seconds,
        "groups": metrics, "failed_groups": failures, "complete": not failures,
        "scoring_calls_attempted": 3, "match": report["match"] if report else None,
        "pending": report["unscored_skill_ids"] if report else None,
        "fresh_conversations": True, "scored_skill_count": sum(r["resume_evidence_strength"] is not None for r in report["skills"]) if report else None,
        **common.frozen_check(root)}
    save_new(folder / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("mode", "wall_seconds", "total_measured_seconds", "match", "pending", "failed_groups")}), flush=True)
    return summary


def run(args):
    root = _require_live(args)
    if (root / "runs").exists() or (root / "run_setup.json").exists():
        raise ValueError("This fixed one-pair comparison cannot be repeated or resumed automatically")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    endpoint, planned = common.endpoint_from_file(args.env_file), read(root / "planned_bindings.json")
    expected = read(root / "cloud_expected.json")
    setup_started = time.perf_counter()
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as client:
            observed = common.snapshot_agents(client, expected)
    if observed != expected:
        raise ValueError("A protected Agent inventory differs before the comparison")
    save_new(root / "cloud_before.json", observed)
    inventory_seconds = time.perf_counter() - setup_started
    values = {"skill_gap_foundry_project_endpoint": endpoint}
    for group in GROUPS:
        values[f"skill_gap_{group}_agent_name"] = planned["original"][group]["name"]
        values[f"skill_gap_{group}_agent_version"] = "2"
    settings = SkillGapSettings(_env_file=None, **values)
    preflight_started = time.perf_counter()
    prepared = native.preflight(GROUPS, lambda g, name, value: _save_event(root / "preflight" / g, name, value), settings=settings)
    preflight_seconds = time.perf_counter() - preflight_started
    bindings = {"entry": planned["entry"], "original": {}}
    for group, item in prepared.items():
        if item.agent_name != planned["original"][group]["name"] or item.agent_version != "2" or sha(item.definition) != expected[item.agent_name]["definitions"]["2"]:
            raise ValueError("Native preflight resolved an unexpected original Agent snapshot")
        bindings["original"][group] = {"name": item.agent_name, "version": item.agent_version, "definition": item.definition}
    save_new(root / "bindings.json", bindings)
    save_new(root / "run_setup.json", {"cloud_inventory_seconds": inventory_seconds,
        "native_preflight_seconds": preflight_seconds, "total_setup_seconds": time.perf_counter() - setup_started,
        "preflight_before_all_inference": True, "model_calls": 0})
    summaries = [_run_arm(root, mode, endpoint, prepared, preflight_seconds) for mode in MODES]
    save_new(root / "comparison_run.json", {"scoring_calls_attempted": 6,
        "complete": all(s["complete"] for s in summaries), "arms": {s["mode"]: s for s in summaries},
        "rounds_per_arm": 1, "additional_model_calls": 0})


def verify(args):
    root = _require_live(args)
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    expected = read(root / "cloud_expected.json")
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=common.endpoint_from_file(args.env_file), credential=credential, allow_preview=True) as client:
            if common.snapshot_agents(client, expected) != expected:
                raise ValueError("An Agent definition or version inventory changed")
    result = {"all_original_and_experimental_agents_unchanged": True, "agent_mutations": 0,
        "application_files_unchanged": True, "all_job_market_unchanged": True, "database_access": False,
        "commit_performed": False, "push_performed": False, **common.frozen_check(root)}
    save_new(root / "isolation_check.json", result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--entry-systems", type=Path)
    parser.add_argument("--entry-others", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare" and (args.entry_systems is None or args.entry_others is None):
        parser.error("prepare requires --entry-systems and --entry-others")
    globals()[args.action](args)


if __name__ == "__main__":
    main()
