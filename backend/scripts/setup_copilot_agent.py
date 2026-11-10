"""Explicitly create or reuse a Copilot version; never run provisioning from a chat request.

Run from backend: python -m scripts.setup_copilot_agent --model YOUR_MODEL_DEPLOYMENT
Requires your own COPILOT_FOUNDRY_PROJECT_ENDPOINT; never uses another Agent's project.
"""
import argparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential

from app.core.config import CopilotSettings
from app.services.copilot.agent import agent_definition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Existing Foundry model deployment name")
    args = parser.parse_args()
    settings = CopilotSettings()
    endpoint = settings.copilot_foundry_project_endpoint
    if not endpoint:
        parser.error("Set COPILOT_FOUNDRY_PROJECT_ENDPOINT first.")
    definition = agent_definition(args.model)
    with DefaultAzureCredential(process_timeout=10) as credential, AIProjectClient(
        endpoint=endpoint, credential=credential, retry_total=0, connection_timeout=10, read_timeout=30
    ) as project:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            versions = list(project.agents.list_versions(settings.copilot_foundry_agent_name, limit=100))
        except ResourceNotFoundError:
            versions = []
        existing = next((version for version in versions if all(
            version.definition.as_dict().get(key) == value for key, value in definition.items())), None)
        version = existing or project.agents.create_version(
            agent_name=settings.copilot_foundry_agent_name,
            definition=PromptAgentDefinition(definition),
            description="CareerGPS Copilot with read-only fictional skill-gap and learning tools.",
        )
        print(f"COPILOT_FOUNDRY_AGENT_NAME={version.name}")
        print(f"COPILOT_FOUNDRY_AGENT_VERSION={version.version}")


if __name__ == "__main__":
    main()
