"""Prepare or score locally; live calls require an explicit --live switch."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from experiments.entry_level_skill_gaps.entry_agents import entry_contract, compact_contract
from app.services.skill_gaps.skill_groups import GROUPS, make_group_payloads
from app.services.skill_gaps.match import summarize_match


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="ascii", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def contract_for(variant):
    return {"entry": entry_contract, "compact": compact_contract}[variant]


def require_pinned_agent(agent):
    if not isinstance(agent, dict) or not isinstance(agent.get("name"), str) or not agent["name"].strip():
        raise ValueError("An explicit Agent name is required.")
    version = agent.get("version")
    if not isinstance(version, str) or not version.isdecimal() or int(version) < 1:
        raise ValueError("Use an explicit positive numeric version, never latest.")


def invoke(payload, agent, folder, endpoint, *, group="diagnostic"):
    """Run one pinned call. Calling this function explicitly opts into live access.

    Azure dependencies and credentials are loaded here only. The returned tuple
    is (parsed_output, metrics). No retries, repairs or saved-Agent updates occur.
    A configured definition, when present, must exactly match the live version.
    """
    require_pinned_agent(agent)
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("An explicit HTTPS project endpoint is required.")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    timings = {}
    save_new(folder / "input.json", payload)
    try:
        with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
            with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project:
                definition = project.agents.get_version(agent["name"], agent["version"]).definition.as_dict()
                if "definition" in agent and definition != agent["definition"]:
                    raise ValueError("Pinned Agent definition differs from the supplied binding.")
                save_new(folder / "agent_binding.json", {
                    "name": agent["name"], "version": agent["version"],
                    "definition_sha256": sha(definition),
                })
                with project.get_openai_client(timeout=480, max_retries=0) as client:
                    timings["sdk_auth_and_definition_seconds"] = time.perf_counter() - started
                    mark = time.perf_counter()
                    conversation = client.conversations.create()
                    timings["conversation_create_seconds"] = time.perf_counter() - mark
                    try:
                        mark = time.perf_counter()
                        response = client.responses.create(
                            conversation=conversation.id,
                            input=[{"role": "user", "content": "Execute " + payload["task"]
                                    + " using your saved Instructions and response format. INPUT_JSON:\n"
                                    + json.dumps(payload, ensure_ascii=False)}],
                            max_output_tokens=40000,
                            extra_body={"agent_reference": {"type": "agent_reference",
                                                           "name": agent["name"], "version": agent["version"]}},
                        )
                        timings["inference_seconds"] = time.perf_counter() - mark
                        raw = response.model_dump(mode="json")
                        save_new(folder / "agent.raw.json", raw)
                        expected_reference = {"type": "agent_reference", "name": agent["name"], "version": agent["version"]}
                        if response.status != "completed" or raw.get("agent_reference") != expected_reference:
                            raise ValueError("Incomplete response or incorrect Agent binding; no automatic retry.")
                        if raw.get("model") != definition["model"]:
                            raise ValueError("Returned model differs from the pinned definition.")
                        if (raw.get("reasoning") or {}).get("effort") != definition.get("reasoning", {}).get("effort"):
                            raise ValueError("Returned reasoning effort differs from the pinned definition.")
                        expected_format = definition.get("text", {}).get("format", {})
                        returned_format = (raw.get("text") or {}).get("format") or {}
                        if returned_format.get("name") != expected_format.get("name") or returned_format.get("strict") is not True:
                            raise ValueError("Returned output contract differs from the pinned definition.")
                        output = json.loads(response.output_text)
                        save_new(folder / "agent.response.json", output)
                    finally:
                        mark = time.perf_counter()
                        try:
                            client.conversations.delete(conversation_id=conversation.id)
                        except Exception:
                            timings["conversation_cleanup_failed"] = True
                        timings["conversation_delete_seconds"] = time.perf_counter() - mark
        timings["group_wall_seconds"] = time.perf_counter() - started
        metrics = {"group": group, "name": agent["name"], "version": agent["version"],
                   "timings": timings, "usage": raw.get("usage")}
        save_new(folder / "metrics.json", metrics)
        return output, metrics
    except Exception as error:
        # Preserve failure type without copying endpoint or credential error text.
        save_new(folder / "failure.json", {"type": type(error).__name__, "automatic_retry": False})
        raise


def weighted_entry(rows, market, family):
    """Apply the existing all-job weights; this function does not assess evidence."""
    result = {"job_family": family, "skills": [],
              "metric": "experimental_entry_level_requirement_coverage",
              "demand_snapshot_fingerprint": market["source_fingerprint"]}
    family_market = market["families"][family]
    count = family_market["total_job_count"]
    if count <= 0:
        raise ValueError("A positive all-job denominator is required.")
    for row in rows:
        counts = family_market["skills"][row["skill_id"]]
        weight = Decimal(counts["required_job_count"] + counts["preferred_only_job_count"]) / Decimal(count)
        score = row["entry_level_score"]
        gap = None if score is None else Decimal(1) - Decimal(str(score))
        result["skills"].append({**row, "resume_evidence_strength": score,
            "skill_gap": None if gap is None else float(gap), "skill_gap_grade": row["entry_level_grade"],
            "demand": {**counts, "N": count}, "demand_weight": round(float(weight), 6),
            "priority": None if gap is None else round(float(weight * gap), 6)})
    result["unscored_skill_ids"] = [r["skill_id"] for r in result["skills"] if r["entry_level_score"] is None]
    result["match"] = summarize_match(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Prepare one group payload offline.")
    prepare.add_argument("--variant", choices=["entry", "compact"], default="compact")
    prepare.add_argument("--group", choices=GROUPS, required=True)
    prepare.add_argument("--input", type=Path, required=True, help="Existing prepared resume input JSON.")
    prepare.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("score", help="Validate and score a saved response offline.")
    score.add_argument("--variant", choices=["entry", "compact"], default="compact")
    score.add_argument("--adapter", help="Optional experiment-local module:function accepting output and payload.")
    score.add_argument("--input", type=Path, required=True)
    score.add_argument("--response", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    live = commands.add_parser("live", help="Run one pinned Agent only with --live.")
    live.add_argument("--live", action="store_true", help="Explicitly allow one live model request.")
    live.add_argument("--config", type=Path, required=True)
    live.add_argument("--input", type=Path, required=True)
    live.add_argument("--output", type=Path, required=True, help="New local run directory.")
    args = parser.parse_args(argv)
    if args.command == "live":
        if not args.live:
            parser.error("Live access requires the explicit --live flag.")
        config = read(args.config)
        invoke(read(args.input), config["agent"], args.output, config["endpoint"])
        return 0
    criteria = read(HERE / "criteria.json")
    if args.command == "prepare":
        payload = make_group_payloads(read(args.input))[args.group]
        save_new(args.output, contract_for(args.variant).build_payload(payload, criteria))
    else:
        payload, response = read(args.input), read(args.response)
        if args.adapter:
            module_name, separator, attribute = args.adapter.partition(":")
            if not separator or not module_name.startswith("experiments.entry_level_skill_gaps."):
                parser.error("Adapters must be functions inside experiments.entry_level_skill_gaps.")
            report = getattr(importlib.import_module(module_name), attribute)(response, payload)
        else:
            catalog = read(BACKEND / "app/services/skill_gaps/data/core_catalog.json")
            report = contract_for(args.variant).assess_output(response, payload, catalog, criteria)
        save_new(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
