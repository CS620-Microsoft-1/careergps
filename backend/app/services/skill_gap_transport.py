"""Web Agent configuration, separate from the preserved v12 experiment.

Check the approved local Instructions and unchanged v12 response schema before
the single inference. Diagnostics contain hashes, never credentials or prompts.
"""
import hashlib
import json
import time

from app.core.config import BACKEND_ROOT
from local_experiments.skill_gap_core_v12.run import ROOT as V12_ROOT
from local_experiments.skill_gap_core_v12.schema import SCHEMA_NAME
from local_experiments.skill_gap_core_v12.transport import create_response, decode_response

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
        format_ = json.loads((V12_ROOT / "response-format.json").read_text(encoding="utf-8"))
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
