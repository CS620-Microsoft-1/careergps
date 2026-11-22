"""Send one checked request to each approved entry-level skill-group Agent."""

from dataclasses import dataclass
import hashlib
import json
from time import perf_counter
from typing import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from app.core.config import SkillGapSettings
from .assets import ASSET_ROOT
from .entry_level import build_format, validate_payload
from .entry_level_agents import (
    AgentBundleError, AgentDefinition, MODEL, REASONING_EFFORT, load_bundle,
)
from .skill_group_transport import PreparedGroup, _definition, _digest, _fail, _field, _file_digest, _groups, _text
from .skill_groups import PARTITION_POLICY_VERSION
from .sources import build_index
from .transport import SkillGapConfigurationError, create_response


TRANSPORT_VERSION = "entry-level-skill-groups.v2"
SCHEMA_NAME = "entry-level-skill-group-formats"
REQUEST_HINT = (
    "Before returning JSON, verify every proof against its skill and criterion's "
    "criterion_unit_ids, even when a source is visible elsewhere. Copy one exact continuous "
    "substring from that unit. For LLM c3 cite the checked model output, not its comparison "
    "reference. If the checked output is unidentified, leave checked_output and detail empty."
)

# Default activation is scoped to the Foundry project where these exact saved
# Agent versions were benchmarked. The endpoint and credentials are supplied
# by the caller's existing application settings.
APPROVED_PROJECT_SHA256 = "22be093e60863a8a335da8876e22f52617d7d6eb68d7bf49cc28123c36cd3d97"


@dataclass(frozen=True)
class PreparedEntryLevelGroup(PreparedGroup):
    family: str


def _endpoint(settings: SkillGapSettings) -> str | None:
    return _text(settings.skill_gap_foundry_project_endpoint)


def can_use_entry_level(settings: SkillGapSettings) -> bool:
    endpoint = _endpoint(settings)
    if not endpoint:
        return False
    try:
        url = urlsplit(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            return False
        normalized = urlunsplit((url.scheme, url.netloc.lower(), url.path.rstrip("/"), "", ""))
    except ValueError:
        return False
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() == APPROVED_PROJECT_SHA256


def _bindings(family: str) -> dict[str, AgentDefinition]:
    if family not in ("ai_engineer", "software_engineer", "data_analyst"):
        raise SkillGapConfigurationError("entry_level_family_unsupported", "The job family has no approved Skill Gap Agents.")
    try:
        bundle = load_bundle()
    except AgentBundleError:
        raise SkillGapConfigurationError("entry_level_bundle_invalid",
            "The repository Agent bundle is missing or differs from the approved configuration. Run the offline Agent check.") from None
    return {group: entry for (entry_family, group), entry in bundle.items() if entry_family == family}


def configuration_signature(settings: SkillGapSettings, family: str) -> dict:
    """Fingerprint locally approved pins without Azure access."""
    bindings = {}
    for group, pin in _bindings(family).items():
        fmt = build_format(group, family)
        bindings[group] = {
            "agent_name": pin.name,
            "agent_version": pin.version,
            "definition_sha256": pin.definition_sha256,
            "instructions_sha256": pin.instructions_sha256,
            "instructions_source": "repository_bundle",
            "schema_name": fmt["name"],
            "schema_sha256": _digest(fmt["schema"]),
        }
    return {
        "transport_version": TRANSPORT_VERSION,
        "strategy": "entry_level_skill_groups",
        "project_endpoint": _endpoint(settings),
        "job_family": family,
        "branches": bindings,
        "schema_name": SCHEMA_NAME,
        "schema_sha256": _digest({g: b["schema_sha256"] for g, b in bindings.items()}),
        "schema_file_sha256": _digest({g: b["schema_sha256"] for g, b in bindings.items()}),
        "catalog_sha256": _file_digest(ASSET_ROOT / "core_catalog.json"),
        "partition_policy_version": PARTITION_POLICY_VERSION,
        "request_hint_sha256": _digest(REQUEST_HINT),
    }


def _matches_format(observed: object, expected: dict) -> bool:
    return (
        isinstance(observed, dict) and observed.get("type") == "json_schema"
        and observed.get("name") == expected["name"] and observed.get("strict") is True
        and observed.get("schema", observed.get("schema_")) == expected["schema"]
    )


def preflight(
    branches: Iterable[str], save: Callable, *, settings: SkillGapSettings, family: str
) -> dict[str, PreparedEntryLevelGroup]:
    """Verify every requested saved definition before starting inference."""
    requested = _groups(branches)
    if not requested:
        return {}
    bindings = _bindings(family)
    group = requested[0]
    endpoint = _endpoint(settings)
    if not endpoint:
        _fail(group, "agent_not_configured", "Set the shared Foundry project endpoint before retrying.", save)
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        prepared = {}
        with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
            with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project:
                for group in requested:
                    pin = bindings[group]
                    expected_format = build_format(group, family)
                    saved = project.agents.get_version(pin.name, pin.version)
                    observed_name, observed_version = _field(saved, "name"), _field(saved, "version")
                    draft = _field(saved, "draft")
                    if draft is None:
                        draft = _field(saved, "is_draft")
                    definition = _definition(_field(saved, "definition"))
                    definition_hash = _digest(definition)
                    instructions = definition.get("instructions")
                    instructions_hash = (hashlib.sha256(instructions.encode("utf-8")).hexdigest()
                                         if isinstance(instructions, str) else None)
                    format_ = _field(definition.get("text"), "format")
                    reasoning = _field(definition.get("reasoning"), "effort")
                    check = {
                        "branch": group, "family": family, "agent_name": pin.name,
                        "agent_version": pin.version, "model_calls": 0,
                        "transport_version": TRANSPORT_VERSION,
                        "pinned_version_match": str(observed_version) == pin.version and observed_name in (None, pin.name)
                        and draft is not True,
                        "definition_sha256": definition_hash,
                        "approved_definition_sha256": pin.definition_sha256,
                        "definition_match": definition_hash == pin.definition_sha256,
                        "instructions_sha256": instructions_hash,
                        "approved_instructions_sha256": pin.instructions_sha256,
                        "instructions_match": instructions_hash == pin.instructions_sha256,
                        "schema_name": expected_format["name"],
                        "schema_match": _matches_format(format_, expected_format),
                        "model_match": definition.get("model") == MODEL,
                        "reasoning_match": reasoning == REASONING_EFFORT,
                    }
                    if not all(check[key] for key in (
                        "pinned_version_match", "definition_match", "instructions_match", "schema_match", "model_match", "reasoning_match",
                    )):
                        _fail(group, "entry_level_binding_mismatch",
                              "The saved Agent differs from the approved entry-level binding. No model call was made.",
                              save, check)
                    save(group, "configuration_check.json", check)
                    save(group, "observed_agent.json", {
                        "branch": group, "family": family, "name": pin.name, "version": pin.version,
                        "draft": draft, "definition": definition, "instructions_source": "foundry",
                    })
                    prepared[group] = PreparedEntryLevelGroup(
                        group, endpoint, pin.name, pin.version, definition, check, family
                    )
        return prepared
    except SkillGapConfigurationError:
        raise
    except Exception:
        _fail(group, "entry_level_agent_unavailable",
              "Could not read or validate the saved entry-level Agent. Check the binding and project access. No model call was made.",
              save)


def invoke_prepared(
    prepared: PreparedEntryLevelGroup, payload: dict, save: Callable, on_request: Callable, timings: dict
) -> dict:
    group, family = prepared.branch, prepared.family
    _groups((group,))
    pin = _bindings(family)[group]
    fmt = build_format(group, family)
    try:
        validated_family, _, _ = validate_payload(group, payload)
        if validated_family != family:
            raise ValueError("The approved Agent is bound to a different family")
        sources = payload["resume_sources"]
        paths = [source["path"] for source in sources]
        paths.extend(unit["path"] for unit in build_index(sources).values())
        if any(not isinstance(path, str) or not path.startswith("/")
               or path.split("/", 2)[1] == "personal_information" for path in paths):
            raise ValueError("An evidence source is outside the allowed resume scope")
    except (ValueError, TypeError, KeyError, AttributeError):
        _fail(group, "scope_mismatch", "The entry-level input does not match its approved family and group.")
    if (prepared.agent_name, prepared.agent_version, _digest(prepared.definition)) != (
        pin.name, pin.version, pin.definition_sha256
    ) or not _matches_format(_field(prepared.definition.get("text"), "format"), fmt):
        _fail(group, "prepared_configuration_changed",
              "The checked Agent definition changed after preflight. No model call was made.")

    reference = {"type": "agent_reference", "name": pin.name, "version": pin.version}
    started = perf_counter()
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
            with AIProjectClient(endpoint=prepared.project_endpoint, credential=credential, allow_preview=True) as project:
                with project.get_openai_client(timeout=480, max_retries=0) as client:
                    timings["sdk_auth_configuration_seconds"] = round(perf_counter() - started, 3)
                    response = create_response(
                        client, payload, on_request, timings, agent_reference=reference, request_hint=REQUEST_HINT
                    )
        raw = response.model_dump(mode="json")
        save("agent.raw.json", raw)
        if (response.status != "completed" or raw.get("agent_reference") != reference or raw.get("model") != MODEL
                or _field(raw.get("reasoning"), "effort") != REASONING_EFFORT
                or not _matches_format(_field(raw.get("text"), "format"), fmt)):
            raise RuntimeError("The response does not match the approved entry-level Agent contract")
        usage = raw.get("usage")
        if isinstance(usage, dict):
            for name in ("input_tokens", "output_tokens", "total_tokens"):
                if isinstance(usage.get(name), int):
                    timings[name] = usage[name]
        return json.loads(response.output_text)
    except SkillGapConfigurationError:
        raise
    except Exception:
        _fail(group, "inference_failed",
              "The saved entry-level Agent could not finish or returned an incompatible response. Check the run artifacts before retrying.")
