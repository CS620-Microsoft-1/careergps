"""Single call to the certification recommendation Agent saved in Foundry.

The Agent's Instructions and response format live in app/prompts/certifications/;
copy them into the Foundry Agent when they change.
"""
import json

from app.core.config import CertificationSettings


class CertificationAgentNotConfigured(RuntimeError):
    """No endpoint or Agent name; callers fall back to gap ranking."""


def is_configured(settings: CertificationSettings | None = None) -> bool:
    settings = settings or CertificationSettings()
    return bool(settings.certification_foundry_project_endpoint and settings.certification_foundry_agent_name)


def invoke(payload: dict, *, timeout_seconds: float = 90.0) -> dict:
    settings = CertificationSettings()
    if not is_configured(settings):
        raise CertificationAgentNotConfigured("The certification Agent is not configured.")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=settings.certification_foundry_project_endpoint,
                             credential=credential, allow_preview=True) as project:
            with project.get_openai_client(agent_name=settings.certification_foundry_agent_name,
                                           timeout=timeout_seconds, max_retries=0) as client:
                conversation = client.conversations.create()
                try:
                    response = client.responses.create(
                        conversation=conversation.id,
                        input=[{"role": "user", "content":
                                "Execute recommend_certifications using your saved Instructions and response format. INPUT_JSON:\n"
                                + json.dumps(payload, ensure_ascii=False)}],
                    )
                finally:
                    try:
                        client.conversations.delete(conversation_id=conversation.id)
                    except Exception:
                        pass
    if response.status != "completed":
        raise RuntimeError("Certification Agent response incomplete")
    return json.loads(response.output_text)
