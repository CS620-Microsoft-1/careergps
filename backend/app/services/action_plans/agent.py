"""Single call to action-plan-agent saved in Foundry.

Its Instructions and response format live in app/prompts/action_plan/; copy them into the Foundry Agent
when they change. No retries: the planner falls back to the rule plan instead.
"""
import json

from app.core.config import ActionPlanSettings

PROMPT = "Execute build_action_plan using your saved Instructions and response format. INPUT_JSON:\n"


class ActionPlanAgentNotConfigured(RuntimeError):
    """No endpoint or Agent name; callers fall back to the rule plan."""


def is_configured(settings: ActionPlanSettings | None = None) -> bool:
    settings = settings or ActionPlanSettings()
    return bool(settings.action_plan_foundry_project_endpoint and settings.action_plan_foundry_agent_name)


def invoke(payload: dict, *, timeout_seconds: float = 90.0, settings: ActionPlanSettings | None = None) -> dict:
    """Send INPUT_JSON to the Agent and return its parsed JSON answer (not yet validated)."""
    settings = settings or ActionPlanSettings()
    if not is_configured(settings):
        raise ActionPlanAgentNotConfigured("The action plan Agent is not configured.")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    name, version = settings.action_plan_foundry_agent_name, settings.pinned_agent_version
    # A pinned version goes in agent_reference (like the Skill Gap and JD Agents); otherwise the
    # client is bound to the Agent's latest version.
    client_options = {} if version else {"agent_name": name}
    request_options = ({"extra_body": {"agent_reference": {"type": "agent_reference", "name": name, "version": version}}}
                       if version else {})
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=settings.action_plan_foundry_project_endpoint,
                             credential=credential, allow_preview=True) as project:
            with project.get_openai_client(timeout=timeout_seconds, max_retries=0, **client_options) as client:
                conversation = client.conversations.create()
                try:
                    response = client.responses.create(
                        conversation=conversation.id,
                        input=[{"role": "user", "content": PROMPT + json.dumps(payload, ensure_ascii=False)}],
                        **request_options,
                    )
                finally:
                    try:
                        client.conversations.delete(conversation_id=conversation.id)
                    except Exception:
                        pass
    if response.status != "completed":
        raise RuntimeError("Action plan Agent response incomplete")
    return json.loads(response.output_text)
