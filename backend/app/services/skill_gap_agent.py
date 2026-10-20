"""Call only the configured Skill Gap Agent, without loading FastAPI or SQLAlchemy."""
import json
import re
from copy import deepcopy
from contextlib import ExitStack

from app.core.config import SkillGapSettings
from app.schemas.skill_gap import AgentInput


class SkillGapAgentError(RuntimeError):
    pass


def response_format(schema: dict, name: str) -> dict:
    """Use a genuine Responses API schema, without changing its nullable semantics."""
    if schema.get("type") != "object":
        raise ValueError("Structured output requires a root object schema.")

    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                properties = node.get("properties", {})
                if node.get("additionalProperties") is not False:
                    raise ValueError("Every structured-output object must forbid additional properties.")
                if set(node.get("required", [])) != set(properties):
                    raise ValueError("Every structured-output property must be required; use nullable types for unknowns.")
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(schema)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]
    if not safe_name:
        raise ValueError("A structured-output schema name is required.")
    return {"type": "json_schema", "name": safe_name, "strict": True, "schema": deepcopy(schema)}


def call_foundry(inputs: AgentInput | dict, prompt: str, settings: SkillGapSettings,
                 *, max_output_tokens: int | None = None, output_schema: dict | None = None,
                 schema_name: str = "skill_gap_response", response_metadata: dict | None = None,
                 reasoning_effort: str | None = None, request_timeout: float = 120) -> str:
    if not settings.skill_gap_foundry_project_endpoint or not settings.skill_gap_foundry_agent_name:
        raise SkillGapAgentError("Set both SKILL_GAP_FOUNDRY_* variables in backend/.env.")
    structured_format = response_format(output_schema, schema_name) if output_schema is not None else None
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        with ExitStack() as stack:
            credential = stack.enter_context(DefaultAzureCredential(exclude_managed_identity_credential=True))
            project = stack.enter_context(AIProjectClient(
                endpoint=settings.skill_gap_foundry_project_endpoint,
                credential=credential, allow_preview=True,
            ))
            client = stack.enter_context(project.get_openai_client(
                agent_name=settings.skill_gap_foundry_agent_name, timeout=request_timeout, max_retries=0,
            ))
            conversation = client.conversations.create()
            try:
                output_options = {"max_output_tokens": max_output_tokens} if max_output_tokens else {}
                if structured_format is not None:
                    output_options["text"] = {"format": structured_format}
                if reasoning_effort is not None:
                    output_options["reasoning"] = {"effort": reasoning_effort}
                response = client.responses.create(
                    conversation=conversation.id,
                    input=[{"role": "user", "content": prompt + "\n\nINPUT_JSON:\n" + json.dumps(
                        inputs.model_dump() if isinstance(inputs, AgentInput) else inputs,
                        ensure_ascii=False, separators=(",", ":"),
                    )}],
                    **output_options,
                )
                status = getattr(response, "status", None)
                usage = getattr(response, "usage", None)
                incomplete = getattr(response, "incomplete_details", None)
                text_config = getattr(response, "text", None)
                reasoning = getattr(response, "reasoning", None)
                refusal = any(getattr(content, "type", None) == "refusal"
                              for item in getattr(response, "output", [])
                              for content in getattr(item, "content", []))
                if response_metadata is not None:
                    response_metadata.update({
                        "response_id": getattr(response, "id", None), "status": status,
                        "model": getattr(response, "model", None), "refused": refusal,
                        "usage": usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage,
                        "incomplete_details": incomplete.model_dump(mode="json") if hasattr(incomplete, "model_dump") else incomplete,
                        "returned_text_config": text_config.model_dump(mode="json") if hasattr(text_config, "model_dump") else text_config,
                        "api_schema_requested": structured_format is not None,
                        "returned_reasoning_config": reasoning.model_dump(mode="json") if hasattr(reasoning, "model_dump") else reasoning,
                    })
                if status not in (None, "completed") or refusal or not response.output_text:
                    if response_metadata is not None:
                        response_metadata["partial_output_text"] = response.output_text
                    raise SkillGapAgentError(f"Foundry did not return a completed usable response (status={status}, refused={refusal}).")
                return response.output_text
            finally:
                try:
                    client.conversations.delete(conversation_id=conversation.id)
                except Exception:
                    pass
    except SkillGapAgentError:
        raise
    except Exception as error:
        status = getattr(error, "status_code", None)
        if response_metadata is not None:
            body = getattr(error, "body", None)
            details = body.get("error", body) if isinstance(body, dict) else {}
            response_metadata["request_error"] = {
                "status": status,
                **{key: str(details[key])[:1500] for key in ("code", "param", "message")
                   if isinstance(details, dict) and details.get(key) is not None},
            }
            headers = getattr(getattr(error, "response", None), "headers", {})
            response_metadata["rate_limit_headers"] = {
                key: headers[key] for key in ("retry-after", "x-ratelimit-limit-tokens",
                    "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens") if key in headers}
        if status in (401, 403) or "Credential" in type(error).__name__ or "Authentication" in type(error).__name__:
            message = "Azure authentication/permission failed. Check az login and access to the new project."
        elif status == 429:
            # Diagnostic timing only; never include request bodies, credentials or server text.
            headers = getattr(getattr(error, "response", None), "headers", {})
            retry_after = headers.get("retry-after", "unknown")
            message = f"Foundry rate limit reached (retry-after={retry_after})."
        else:
            message = f"Foundry request failed ({type(error).__name__}, status={status})."
        raise SkillGapAgentError(message) from None
