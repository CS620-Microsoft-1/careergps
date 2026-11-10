"""Stateless Foundry orchestration with bounded, server-dispatched mock tools."""
from contextlib import ExitStack
from time import monotonic

from app.core.config import BACKEND_ROOT, CopilotSettings
from app.schemas.copilot import AgentAnswer, CopilotReply, CopilotRequest
from app.services.copilot.tools import TOOLS, MockCopilotTools, ToolContext

INSTRUCTIONS = BACKEND_ROOT / "app/prompts/copilot/Instructions.md"
MAX_ROUNDS = 4
MAX_TOOL_CALLS = 4


def agent_definition(model: str) -> dict:
    return {"kind": "prompt", "model": model, "instructions": INSTRUCTIONS.read_text(encoding="utf-8"),
            "tools": TOOLS, "text": {"format": {"type": "json_schema", "name": "copilot_answer",
                "strict": True, "schema": AgentAnswer.model_json_schema()}}}


def matches_contract(definition: dict) -> bool:
    expected = agent_definition(definition.get("model", ""))
    return all(definition.get(key) == expected[key] for key in ("kind", "instructions", "tools", "text"))


class CopilotError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def run_orchestrator(client, reference: dict, request: CopilotRequest, tools: MockCopilotTools,
                     *, deadline: float) -> CopilotReply:
    # History remains untrusted user content, never promoted to developer instructions.
    inputs = [{"role": "user", "content": request.model_dump_json()}]
    evidence = {}
    evidence_by_tool: dict[str, set[str]] = {}
    call_ids: set[str] = set()
    for _ in range(MAX_ROUNDS):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CopilotError("Copilot timed out. Please try again.", 504)
        response = client.responses.create(
            input=inputs, store=False, max_output_tokens=4000, include=["reasoning.encrypted_content"],
            extra_body={"agent_reference": reference}, timeout=min(30.0, remaining),
        )
        if monotonic() > deadline:
            raise CopilotError("Copilot timed out. Please try again.", 504)
        if response.status != "completed":
            raise CopilotError("Copilot did not complete its response. Please try again.")
        outputs = [item.model_dump(exclude_none=True) for item in response.output]
        if any(item.get("type") not in {"function_call", "message", "reasoning"} for item in outputs):
            raise CopilotError("Copilot returned an unsupported response.")
        calls = [item for item in outputs if item["type"] == "function_call"]
        if calls:
            # Carry opaque reasoning and call items only within this request. Nothing is persisted.
            inputs.extend(outputs)
            for call in calls:
                call_id = call["call_id"]
                if call_id in call_ids or len(call_ids) >= MAX_TOOL_CALLS:
                    raise CopilotError("Copilot reached its tool limit. Try a more specific question.")
                call_ids.add(call_id)
                result = tools.dispatch(call["name"], call["arguments"])
                if result.status == "ok":
                    evidence.update({source.id: source for source in result.sources})
                    evidence_by_tool.setdefault(call["name"], set()).update(source.id for source in result.sources)
                inputs.append({"type": "function_call_output", "call_id": call_id,
                               "output": result.model_dump_json()})
            continue
        try:
            answer = AgentAnswer.model_validate_json(response.output_text)
        except ValueError:
            raise CopilotError("Copilot returned an invalid answer. Please try again.") from None
        ids = list(dict.fromkeys(answer.source_ids))
        if any(source_id not in evidence for source_id in ids):
            raise CopilotError("Copilot could not verify its evidence. Please try again.")
        required = {"explain_gap": ["get_skill_gap_analysis"],
                    "learning_advice": ["get_skill_gap_analysis", "get_learning_suggestions"]}.get(answer.intent, [])
        if any(not set(ids).intersection(evidence_by_tool.get(name, set())) for name in required):
            raise CopilotError("Copilot did not retrieve the evidence needed for this answer.")
        if answer.intent == "unsupported_action":
            answer.text = ("This version can explain sample skill gaps and suggest learning or projects. "
                           "It cannot modify your profile, save settings or plans, or start an analysis. No changes were made.")
            ids = []
        return CopilotReply(text=answer.text, sources=[evidence[source_id] for source_id in ids], intent=answer.intent)
    raise CopilotError("Copilot reached its response limit. Try a more specific question.")


class FoundryCopilotService:
    def __init__(self, settings: CopilotSettings):
        self.settings = settings

    def chat(self, request: CopilotRequest, context: ToolContext) -> CopilotReply:
        settings = self.settings
        if not settings.copilot_foundry_project_endpoint or not settings.copilot_foundry_agent_version or settings.copilot_foundry_agent_version == "latest":
            raise CopilotError("Copilot is not configured. Set its project endpoint and a concrete Agent version.", 503)
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
            deadline = monotonic() + settings.copilot_timeout_seconds
            with ExitStack() as stack:
                credential = stack.enter_context(DefaultAzureCredential(process_timeout=10))
                project = stack.enter_context(AIProjectClient(endpoint=settings.copilot_foundry_project_endpoint,
                    credential=credential, retry_total=0, connection_timeout=10, read_timeout=15))
                version = project.agents.get_version(settings.copilot_foundry_agent_name, settings.copilot_foundry_agent_version)
                if not matches_contract(version.definition.as_dict()):
                    raise CopilotError("Copilot Agent does not match the local tool and response contracts. Run the setup script.", 503)
                client = stack.enter_context(project.get_openai_client(timeout=30, max_retries=0))
                return run_orchestrator(client, {"type": "agent_reference", "name": settings.copilot_foundry_agent_name,
                    "version": settings.copilot_foundry_agent_version}, request, MockCopilotTools(context), deadline=deadline)
        except CopilotError:
            raise
        except Exception as error:
            name = type(error).__name__
            status = getattr(error, "status_code", None)
            if status == 429 or "RateLimit" in name:
                raise CopilotError("Copilot is busy. Please try again shortly.", 429) from None
            if isinstance(error, TimeoutError) or "Timeout" in name:
                raise CopilotError("Copilot timed out. Please try again.", 504) from None
            if status in (401, 403, 404) or "Credential" in name or "Authentication" in name:
                raise CopilotError("Copilot is unavailable. Check its Azure login and Agent configuration.", 503) from None
            raise CopilotError("Copilot could not complete the request. Please try again.") from None
