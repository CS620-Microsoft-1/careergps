"""Skill Gap Agent configuration and single-call transport.

Check the approved local Instructions and unchanged response schema before
the single inference. Diagnostics contain hashes, never credentials or prompts.
"""
import hashlib
import json
import time

from app.core.config import BACKEND_ROOT
from .assets import ASSET_ROOT
from .schema import SCHEMA_NAME

ACTIVE_INSTRUCTIONS_PATH = BACKEND_ROOT / "app" / "prompts" / "skill_gaps" / "Instructions.md"
ACTIVE_PROMPT_REVISION = "method-selection.v1"


class SkillGapConfigurationError(RuntimeError):
    def __init__(self, code: str, public_message: str):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def load_local_contract() -> tuple[str, dict]:
    try:
        instructions = ACTIVE_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        format_ = json.loads((ASSET_ROOT / "response-format.json").read_text(encoding="utf-8"))
        if not instructions.strip() or not isinstance(format_, dict) or "schema" not in format_:
            raise ValueError("Local contract is empty")
        return instructions, format_
    except (OSError, ValueError):
        raise SkillGapConfigurationError("local_contract_unavailable",
            "The local Skill Gap configuration is unavailable. Restore the approved Instructions and Schema, then retry.") from None


def validate_definition(definition: dict, version: str | None, save) -> dict:
    instructions, expected_format = load_local_contract()
    definition = definition if isinstance(definition, dict) else {}
    observed = definition.get("instructions")
    observed = observed if isinstance(observed, str) else ""
    text = definition.get("text")
    format_ = text.get("format") if isinstance(text, dict) else {}
    format_ = format_ if isinstance(format_, dict) else {}
    schema = format_.get("schema") or format_.get("schema_")
    expected_text, observed_text = " ".join(instructions.split()), " ".join(observed.split())
    instructions_match = observed_text == expected_text
    schema_match = (format_.get("type") == "json_schema" and format_.get("name") == SCHEMA_NAME
                    and format_.get("strict") is True and schema == expected_format["schema"])
    diagnostics = {"agent_version": version, "prompt_revision": ACTIVE_PROMPT_REVISION,
                   "instructions_match": instructions_match, "schema_match": schema_match,
                   "hash_scope": "canonical_json; instruction whitespace collapsed; run.json separately stores raw file SHA-256",
                   "expected_instructions_sha256": _digest(expected_text),
                   "observed_instructions_sha256": _digest(observed_text),
                   "expected_schema_sha256": _digest(expected_format["schema"]),
                   "observed_schema_sha256": _digest(schema), "model_calls": 0}
    save("configuration_check.json", diagnostics)
    if not version:
        raise SkillGapConfigurationError("agent_version_unavailable",
            "The configured Skill Gap Agent has no saved version. Save its configuration in Azure, then retry.")
    if not schema_match:
        raise SkillGapConfigurationError("schema_mismatch",
            "The Azure Agent response Schema differs from the local Schema. Synchronize the response format, then retry.")
    if not instructions_match:
        raise SkillGapConfigurationError("instructions_mismatch",
            "The Azure Agent Instructions differ from the local version. Synchronize the Instructions and restart the local API, then retry. No model call was made.")
    return diagnostics


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
        raise SkillGapConfigurationError("agent_not_configured",
            "The local Skill Gap Agent connection is not configured. Set its project endpoint and Agent name, then retry.")
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=settings.skill_gap_foundry_project_endpoint,
                             credential=credential, allow_preview=True) as project:
            version = next(iter(project.agents.list_versions(
                settings.skill_gap_foundry_agent_name, limit=1, order="desc", include_drafts=True)), None)
            definition = version.definition.as_dict() if version else {}
            validate_definition(definition, str(version.version) if version else None, save)
            save("observed_agent.json", {"name": settings.skill_gap_foundry_agent_name,
                                        "version": str(version.version), "definition": definition})
            with project.get_openai_client(agent_name=settings.skill_gap_foundry_agent_name,
                                           timeout=480, max_retries=0) as client:
                timings["sdk_auth_configuration_seconds"] = round(time.perf_counter() - started, 3)
                response = create_response(client, payload, on_request, timings)
    return decode_response(response, save)
