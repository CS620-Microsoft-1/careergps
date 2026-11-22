"""Check, create or verify the nine versioned CareerGPS entry-level Agents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import SkillGapSettings
from app.services.skill_gaps.entry_level_agents import (
    AgentBundleError, BUNDLE_ROOT, load_bundle, manage_agents,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "create", "verify"),
                        help="check is offline; create only creates missing names; verify only reads Foundry")
    parser.add_argument("--bundle", type=Path, default=BUNDLE_ROOT, help="Root of the reviewed Agent bundle")
    parser.add_argument("--endpoint", help="Foundry project endpoint; defaults to SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT")
    args = parser.parse_args(argv)
    try:
        bundle = load_bundle(args.bundle)
        if args.command == "check":
            results = [{"family": entry.family, "group": entry.group, "name": entry.name,
                        "version": entry.version, "action": "checked", "definition_sha256": entry.definition_sha256}
                       for entry in bundle.values()]
        else:
            endpoint = args.endpoint or SkillGapSettings().skill_gap_foundry_project_endpoint
            parsed = urlsplit(endpoint or "")
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment):
                raise AgentBundleError("Set a valid HTTPS Foundry project endpoint using --endpoint or environment settings")
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
                with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as client:
                    results = manage_agents(client, bundle, create=args.command == "create")
        print(json.dumps({"command": args.command, "agent_count": len(results), "agents": results}, indent=2))
        return 0
    except AgentBundleError as exc:
        print(f"Agent configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Do not dump tokens, complete prompts or remote response bodies.
        print(f"Foundry operation failed ({type(exc).__name__}). Check project access and Azure authentication.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
