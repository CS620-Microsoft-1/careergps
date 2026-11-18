"""Explicitly preview or synchronize the main conversation Agent in your own project.

Run from backend: python -m scripts.setup_copilot_agent --model YOUR_MODEL_DEPLOYMENT --dry-run
Remove --dry-run only when cloud creation has been explicitly authorized.
"""
import argparse
import json

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential

from app.core.config import CopilotSettings
from app.services.copilot.agent import agent_definition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Existing Foundry model deployment for main")
    parser.add_argument("--dry-run", action="store_true", help="Print the definition without any cloud access")
    args = parser.parse_args()
    settings = CopilotSettings()
    name = settings.orchestrator_foundry_agent_name
    if not name:
        parser.error("Configure the main Copilot Agent name.")
    definition = agent_definition(args.model)
    if args.dry_run:
        print(json.dumps([{"role": "main", "name": name, "definition": definition}],
                         ensure_ascii=False, indent=2))
        return
    endpoint = settings.orchestrator_foundry_project_endpoint
    if not endpoint:
        parser.error("Set your own ORCHESTRATOR_FOUNDRY_PROJECT_ENDPOINT first.")
    with DefaultAzureCredential(process_timeout=10) as credential, AIProjectClient(
        endpoint=endpoint, credential=credential, retry_total=0, connection_timeout=10, read_timeout=30
    ) as project:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            versions = list(project.agents.list_versions(name, limit=100))
        except ResourceNotFoundError:
            versions = []
        existing = next((version for version in versions if all(
            version.definition.as_dict().get(key) == value for key, value in definition.items())), None)
        version = existing or project.agents.create_version(
            agent_name=name, definition=PromptAgentDefinition(definition),
            description="CareerGPS Copilot single main Agent with authenticated resume and saved-report reads only.",
        )
        print(f"ORCHESTRATOR_FOUNDRY_AGENT_NAME={version.name}")
        print(f"ORCHESTRATOR_FOUNDRY_AGENT_VERSION={version.version}")


if __name__ == "__main__":
    main()
