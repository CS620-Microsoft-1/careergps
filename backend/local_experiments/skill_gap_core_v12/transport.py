"""One bound saved-Agent inference, with integrity checking after the response, without repair."""
import json
from pathlib import Path
import time
from .schema import SCHEMA_NAME


def decode_response(response, save):
    raw = response.model_dump(mode="json")
    save("agent.raw.json", raw)
    # Transport/version compatibility only: no content, keys, IDs or quotes
    # from the generated evidence object are checked here.
    if response.status != "completed":
        raise RuntimeError("Agent response incomplete; raw response saved. No automatic retry or repair")
    fmt = (raw.get("text") or {}).get("format") or {}
    if fmt.get("name") != SCHEMA_NAME or fmt.get("type") != "json_schema" or fmt.get("strict") is not True:
        raise RuntimeError("Bound endpoint served a different response format; raw response saved, no score generated")
    return json.loads(response.output_text)


def create_response(client, payload, on_request=lambda: None, timings=None):
    timings = {} if timings is None else timings
    started = time.perf_counter()
    conversation = client.conversations.create()
    timings["conversation_create_seconds"] = round(time.perf_counter() - started, 3)
    try:
        on_request()
        started = time.perf_counter()
        try:
            return client.responses.create(
                conversation=conversation.id,
                input=[{"role": "user", "content":
                        "Execute extract_resume_evidence using your saved Instructions and response format. INPUT_JSON:\n"
                        + json.dumps(payload, ensure_ascii=False)}],
                max_output_tokens=40000,
            )
        finally:
            timings["inference_seconds"] = round(time.perf_counter() - started, 3)
    finally:
        started = time.perf_counter()
        try:
            client.conversations.delete(conversation_id=conversation.id)
        except Exception:
            pass
        timings["conversation_delete_seconds"] = round(time.perf_counter() - started, 3)


def invoke(payload, save, on_request=lambda: None, timings=None):
    timings = {} if timings is None else timings
    started = time.perf_counter()
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from app.core.config import SkillGapSettings

    settings = SkillGapSettings()
    if not settings.skill_gap_foundry_project_endpoint or not settings.skill_gap_foundry_agent_name:
        raise RuntimeError("Set SKILL_GAP_FOUNDRY_PROJECT_ENDPOINT and SKILL_GAP_FOUNDRY_AGENT_NAME in backend/.env")
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=settings.skill_gap_foundry_project_endpoint,
                             credential=credential, allow_preview=True) as project:
            # Compatibility check of saved configuration only; reference validation happens after the single response.
            version = next(iter(project.agents.list_versions(
                settings.skill_gap_foundry_agent_name, limit=1, order="desc", include_drafts=True)), None)
            definition = version.definition.as_dict() if version else {}
            fmt = (definition.get("text") or {}).get("format") or {}
            local_format = json.loads(Path(__file__).with_name("response-format.json").read_text(encoding="utf-8"))
            local_instructions = Path(__file__).with_name("Instructions.md").read_text(encoding="utf-8")
            same_instructions = " ".join(definition.get("instructions", "").split()) == " ".join(local_instructions.split())
            saved_schema = fmt.get("schema") or fmt.get("schema_")
            if (fmt.get("name") != SCHEMA_NAME or fmt.get("strict") is not True
                    or saved_schema != local_format["schema"] or not same_instructions):
                raise RuntimeError("Replace saved Instructions AND response format with core_v12 before testing")
            save("observed_agent.json", {"name": settings.skill_gap_foundry_agent_name,
                                        "version": str(version.version), "definition": definition})
            with project.get_openai_client(agent_name=settings.skill_gap_foundry_agent_name,
                                           timeout=480, max_retries=0) as client:
                timings["sdk_auth_configuration_seconds"] = round(time.perf_counter() - started, 3)
                response = create_response(client, payload, on_request, timings)
    return decode_response(response, save)
