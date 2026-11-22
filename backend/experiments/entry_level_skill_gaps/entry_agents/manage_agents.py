"""Export an experimental Agent plan; create a new unique name only with --create."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import uuid

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from experiments.entry_level_skill_gaps.entry_agents.run_experiment import read, save_new, contract_for
from app.services.skill_gaps.skill_groups import GROUPS


def build_plan(variant, group, model, *, name_prefix="skill-gap-experiment", run_id=None):
    """Return a new-name plan without Azure imports, credentials or network access."""
    if not re.fullmatch(r"skill-gap-experiment(?:-[a-z0-9]+)*", name_prefix):
        raise ValueError("Use a new skill-gap-experiment name prefix, never an application Agent name.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("An explicit deployment name is required.")
    if group not in GROUPS:
        raise ValueError("Unknown group.")
    run_id = run_id or uuid.uuid4().hex[:16]
    if not re.fullmatch(r"[a-z0-9]{8,32}", run_id):
        raise ValueError("Run IDs must contain 8-32 lowercase letters or digits.")
    module = contract_for(variant)
    criteria = read(HERE / "criteria.json")
    catalog = read(BACKEND / "app/services/skill_gaps/data/core_catalog.json")
    prompt = ((HERE / "prompts" / f"{group}.txt").read_text(encoding="ascii")
              if variant == "entry" else module.build_instructions(group))
    name = f"{name_prefix}-{group}-{variant}-{run_id}"
    if len(name) > 63:
        raise ValueError("Experimental names must be at most 63 characters.")
    return {"name": name, "definition": {
        "kind": "prompt", "model": model, "instructions": prompt,
        "reasoning": {"effort": "medium"}, "tools": [],
        "text": {"format": {"type": "json_schema", **module.build_format(catalog, group, criteria)}},
    }}


def create_new(plan, endpoint):
    """Create only a previously absent experimental name; no update API is used."""
    if not plan["name"].startswith("skill-gap-experiment-"):
        raise ValueError("Only isolated experimental names may be created.")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("An explicit HTTPS project endpoint is required.")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from azure.core.exceptions import ResourceNotFoundError

    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as client:
            try:
                client.agents.get(plan["name"])
            except ResourceNotFoundError:
                pass
            else:
                raise ValueError("Agent name already exists; no version will be added.")
            created = client.agents.create_version(plan["name"], body={
                "definition": plan["definition"],
                "description": "Isolated entry-level experiment; application Agents and routing unchanged.",
                "metadata": {"scope": "entry-level-experiment"},
            })
            if str(created.version) != "1" or created.definition.as_dict() != plan["definition"]:
                raise RuntimeError("Unexpected create result; preserve the error and inspect the new experimental name.")
            return {"name": plan["name"], "version": str(created.version), "definition": created.definition.as_dict()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["entry", "compact"], default="compact")
    parser.add_argument("--group", choices=GROUPS, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New plan/config file; never overwritten.")
    parser.add_argument("--create", action="store_true", help="Explicitly allow creating a new cloud Agent.")
    parser.add_argument("--endpoint", help="Project endpoint; required only with --create.")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; refusing to overwrite it.")
    plan = build_plan(args.variant, args.group, args.model)
    if args.create:
        if not args.endpoint:
            parser.error("--endpoint is required with --create.")
        binding = create_new(plan, args.endpoint)
        save_new(args.output, {"endpoint": args.endpoint, "agent": binding})
    else:
        save_new(args.output, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
