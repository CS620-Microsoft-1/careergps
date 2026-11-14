"""Isolated fixed-evidence control/rules comparison; cloud access is explicit.

Creates three new experimental Agent names, with a control version and a rules
version under each. Existing Agent names and application files are read-only.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

from experiments.entry_level_skill_gaps.entry_agents.run_experiment import (
    invoke, read, save_new, sha, weighted_entry,
)
from app.services.skill_gaps.skill_groups import GROUPS, make_group_payloads

HERE = Path(__file__).resolve().parent
MODES = ("control", "rules")


def utc():
    return datetime.now(timezone.utc).isoformat()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def endpoint_from_file(path):
    from dotenv import dotenv_values
    values = dotenv_values(path)
    endpoint = values.get("SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint or not endpoint.startswith("https://"):
        raise ValueError("A configured Skill Gap project endpoint is required")
    return endpoint


def frozen_check(root):
    frozen = read(root / "frozen_files.json")
    changed = [p for p, digest in frozen.items() if not Path(p).is_file() or file_sha(p) != digest]
    if changed:
        raise ValueError("Frozen experiment or protected application files changed")
    return {"frozen_files_verified": len(frozen)}


def snapshot_agents(client, names):
    result = {}
    for name in sorted(set(names)):
        versions = list(client.agents.list_versions(name, limit=100, order="desc", include_drafts=False))
        if len(versions) >= 100:
            raise ValueError("Version inventory exceeds the bounded snapshot limit")
        result[name] = {
            "versions": [str(v.version) for v in versions],
            "definitions": {str(v.version): sha(client.agents.get_version(name, str(v.version)).definition.as_dict()) for v in versions},
        }
    return result


def definition_for(group, family, mode, model):
    from . import contract
    return {
        "kind": "prompt", "model": model,
        "instructions": contract.build_instructions(group, mode),
        "reasoning": {"effort": "medium"}, "tools": [],
        "text": {"format": {"type": "json_schema", **contract.build_format(group, family)}},
    }


def prepare(args):
    from . import contract
    from ..skill_rules.validate_rules import load_bundle, validate_bundle
    start = time.perf_counter()
    root = args.directory.resolve()
    base = read(root / "source_input.json")
    packet = read(root / "evidence_packet.json")
    family = base["job_family"]
    market = read(args.market)
    if validate_bundle(load_bundle())["errors"]:
        raise ValueError("Rule catalog integrity checks failed")
    if market["families"][family]["total_job_count"] <= 0:
        raise ValueError("All-job demand snapshot is required")
    groups = make_group_payloads(base)
    payloads = {mode: {group: contract.build_payload(groups[group], packet, variant=mode) for group in GROUPS} for mode in MODES}
    run_id = uuid.uuid4().hex[:8]
    names = {g: f"skill-gap-experiment-entry-level-{g}-{run_id}" for g in GROUPS}
    if any(len(n) > 63 for n in names.values()):
        raise ValueError("Agent name exceeds platform length")
    definitions = {mode: {g: definition_for(g, family, mode, args.model) for g in GROUPS} for mode in MODES}
    for mode in MODES:
        for group in GROUPS:
            save_new(root / "prepared" / f"{mode}_{group}.json", payloads[mode][group])
            save_new(root / "definitions" / f"{mode}_{group}.json", definitions[mode][group])
    save_new(root / "all_job_market.json", market)
    protected_names = {"skill-gap-foundation", "skill-gap-lifecycle", "skill-gap-systems"}
    for path in args.protect_bindings:
        binding = read(path)
        entries = [binding] if "name" in binding else list(binding.values())
        protected_names.update(item["name"] for item in entries)
    if set(names.values()) & protected_names:
        raise ValueError("New names must not overlap protected Agents")
    schedule = []
    for rep in range(1, args.rounds + 1):
        for mode in (MODES if rep % 2 else tuple(reversed(MODES))):
            schedule.append({"round": rep, "mode": mode})
    plan = {
        "experiment": "entry-level-fixed-evidence-rules.v2", "created_utc": utc(),
        "family": family, "rounds_per_variant": args.rounds, "planned_scoring_calls": 6 * args.rounds,
        "schedule": schedule, "agent_names": names, "protected_agent_names": sorted(protected_names),
        "model": args.model, "reasoning_effort": "medium", "new_agent_count": 3,
        "control_definition": "Existing general criterion semantics in a new shared fixed-evidence protocol; not the unchanged production pipeline.",
        "rules_definition": "Per-skill operational conditions and partial permissions from the frozen full rule catalog.",
        "source_sha256": sha(base), "packet_sha256": sha(packet), "market_sha256": sha(market),
        "all_job_family_count": market["families"][family]["total_job_count"],
        "payload_sha256": {mode: {g: sha(p) for g, p in values.items()} for mode, values in payloads.items()},
        "definition_sha256": {mode: {g: sha(d) for g, d in values.items()} for mode, values in definitions.items()},
        "automatic_retries": 0, "automatic_repairs": False, "runtime_integration": False,
        "scope_limit": "One previously used confirmed resume; reviewer-frozen evidence, not end-to-end extraction or independent population validation.",
        "timing_scope": "Three parallel calls including client/auth, definition verification, conversations, inference, cleanup and local scoring; input preparation and provisioning reported separately.",
        "payload_preparation_seconds": time.perf_counter() - start,
        "full_evidence_review_preparation_seconds": None,
        "preparation_limit": "Payload assembly is timed; earlier reviewer source selection was not timed and is excluded from call latency.",
        "stopping_rule": "Complete the fixed schedule, preserve all errors and outputs, do not change rules or evidence in response to live results.",
    }
    save_new(root / "plan.json", plan)
    paths = [p for p in root.rglob("*.json") if p.is_file()]
    paths += [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += [p for p in (HERE.parent / "skill_rules").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += [p for p in (HERE.parents[1] / "entry_agents").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    for protected in args.protect_root:
        paths += [p for p in protected.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".json", ".toml", ".yaml", ".yml"}]
    paths += [args.market, *args.protect_file]
    save_new(root / "frozen_files.json", {str(p.resolve()): file_sha(p) for p in sorted(set(paths))})
    print(json.dumps({"prepared": True, "rounds": args.rounds, "scoring_calls": 6 * args.rounds,
                      "family": family, "all_job_count": plan["all_job_family_count"],
                      "input_characters": {m: {g: len(json.dumps(p)) for g, p in values.items()} for m, values in payloads.items()}}), flush=True)


def provision(args):
    if not args.live:
        raise ValueError("Provisioning requires --live")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from azure.core.exceptions import ResourceNotFoundError
    root = args.directory.resolve()
    frozen_check(root)
    plan = read(root / "plan.json")
    started = time.perf_counter()
    bindings = {mode: {} for mode in MODES}
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=endpoint_from_file(args.env_file), credential=credential, allow_preview=True) as client:
            before = snapshot_agents(client, plan["protected_agent_names"])
            save_new(root / "cloud_before.json", before)
            for group, name in plan["agent_names"].items():
                if not name.startswith("skill-gap-experiment-entry-level-") or name in before:
                    raise ValueError("Protected or nonexperimental Agent name")
                try:
                    client.agents.get(name)
                except ResourceNotFoundError:
                    continue
                raise ValueError("Experimental Agent already exists; refuse mutation")
            for group, name in plan["agent_names"].items():
                for version, mode in enumerate(MODES, 1):
                    definition = read(root / "definitions" / f"{mode}_{group}.json")
                    if sha(definition) != plan["definition_sha256"][mode][group]:
                        raise ValueError("Planned definition changed")
                    if version == 2:
                        existing = snapshot_agents(client, [name])[name]
                        if existing != {"versions": ["1"], "definitions": {"1": sha(bindings["control"][group]["definition"])}}:
                            raise ValueError("Newly owned experimental Agent changed before rules version")
                    result = client.agents.create_version(name, body={
                        "definition": definition,
                        "description": f"Isolated entry-level {mode} version; fixed evidence and all-job demand; no application routing.",
                        "metadata": {"experiment": plan["experiment"], "variant": mode},
                    })
                    binding = {"name": name, "version": str(result.version), "definition": result.definition.as_dict()}
                    save_new(root / "bindings" / f"{mode}_{group}.json", binding)
                    if binding["version"] != str(version) or binding["definition"] != definition:
                        raise ValueError("Created Agent differs from plan; preserve record and stop")
                    bindings[mode][group] = binding
                    print(json.dumps({"created": name, "variant": mode, "version": str(version)}), flush=True)
            if snapshot_agents(client, plan["protected_agent_names"]) != before:
                raise ValueError("Protected Agent snapshot changed")
    save_new(root / "bindings.json", bindings)
    save_new(root / "provisioning.json", {"seconds": time.perf_counter() - started, "new_names": 3, "versions_per_name": 2,
                                        "protected_agents_unchanged": True})


def run(args):
    if not args.live:
        raise ValueError("Scoring requires --live")
    from . import contract
    root = args.directory.resolve()
    frozen_check(root)
    plan, bindings = read(root / "plan.json"), read(root / "bindings.json")
    market = read(root / "all_job_market.json")
    endpoint = endpoint_from_file(args.env_file)
    for call in plan["schedule"]:
        folder = root / "runs" / f"{call['mode']}_{call['round']:02}"
        # Explicit resume skips every saved round, including failures; no paid call is retried.
        if args.resume and (folder / "summary.json").exists():
            continue
        folder.mkdir(parents=True, exist_ok=False)
        frozen_check(root)
        payloads = {g: read(root / "prepared" / f"{call['mode']}_{g}.json") for g in GROUPS}
        for group in GROUPS:
            if sha(payloads[group]) != plan["payload_sha256"][call["mode"]][group]:
                raise ValueError("Frozen input changed")
            if sha(bindings[call["mode"]][group]["definition"]) != plan["definition_sha256"][call["mode"]][group]:
                raise ValueError("Binding definition changed")
        save_new(folder / "scope.json", {**call, "started_utc": utc(), "market_sha256": sha(market),
                                          "packet_sha256": plan["packet_sha256"], "versions_pinned": True})
        started = time.perf_counter()
        outputs, metrics, failures = {}, {}, {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(invoke, payloads[g], bindings[call["mode"]][g], folder / g, endpoint, group=g): g for g in GROUPS}
            for future in as_completed(futures):
                group = futures[future]
                try:
                    outputs[group], metrics[group] = future.result()
                except Exception as error:
                    failures[group] = {"type": type(error).__name__, "automatic_retry": False}
        call_wall = time.perf_counter() - started
        reports = {}
        for group, output in outputs.items():
            try:
                reports[group] = contract.assess_output(output, payloads[group])
                save_new(folder / group / "assessment.json", reports[group])
            except Exception as error:
                failures[group] = {"type": type(error).__name__, "phase": "local_assessment", "automatic_retry": False}
                save_new(folder / group / "assessment_failure.json", failures[group])
        report = None
        if not failures:
            try:
                report = weighted_entry([row for g in GROUPS for row in reports[g]["skills"]], market, plan["family"])
                save_new(folder / "entry_report.json", report)
            except Exception as error:
                failures["aggregation"] = {"type": type(error).__name__, "phase": "local_aggregation", "automatic_retry": False}
                save_new(folder / "aggregation_failure.json", failures["aggregation"])
        summary = {**call, "wall_seconds": time.perf_counter() - started, "parallel_call_wall_seconds": call_wall,
                   "groups": metrics, "failed_groups": failures, "complete": not failures,
                   "entry_match": report["match"] if report else None,
                   "pending": report["unscored_skill_ids"] if report else None,
                   "scoring_calls_attempted": 3, **frozen_check(root)}
        save_new(folder / "summary.json", summary)
        print(json.dumps({k: summary[k] for k in ("mode", "round", "wall_seconds", "entry_match", "pending", "failed_groups")}), flush=True)


def verify(args):
    if not args.live:
        raise ValueError("Cloud verification requires --live")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    root = args.directory.resolve()
    local = frozen_check(root)
    plan, bindings = read(root / "plan.json"), read(root / "bindings.json")
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=endpoint_from_file(args.env_file), credential=credential, allow_preview=True) as client:
            unchanged = snapshot_agents(client, plan["protected_agent_names"]) == read(root / "cloud_before.json")
            created = snapshot_agents(client, plan["agent_names"].values())
            expected = {name: {"versions": ["2", "1"], "definitions": {
                bindings[m][g]["version"]: sha(bindings[m][g]["definition"]) for m in MODES}}
                for g, name in plan["agent_names"].items()}
            if not unchanged or created != expected:
                raise ValueError("Final cloud isolation check failed")
    result = {"protected_agents_unchanged": True, "new_experimental_agents_match": True,
              "application_files_unchanged": True, "commit_performed": False, "push_performed": False,
              "database_access": False, **local}
    save_new(root / "isolation_check.json", result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "provision", "run", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--market", type=Path)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--protect-root", type=Path, action="append", default=[])
    parser.add_argument("--protect-file", type=Path, action="append", default=[])
    parser.add_argument("--protect-bindings", type=Path, action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 2 <= args.rounds <= 5:
        parser.error("Use two to five planned repetitions per variant")
    if args.action == "prepare" and args.market is None:
        parser.error("prepare requires --market")
    if args.action != "prepare" and args.env_file is None:
        parser.error("live actions require --env-file")
    globals()[args.action](args)


if __name__ == "__main__":
    main()
