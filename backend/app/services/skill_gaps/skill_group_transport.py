"""Approved, immutable saved-Agent snapshots for skill-group experiments.

Only the internal extraction contract is grouped. The public v12 report and
scoring contract stay in their existing modules. Importing or fingerprinting
this module never creates an Azure client or starts a model request.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
import re
from typing import Callable, Iterable

from app.core.config import BACKEND_ROOT, SkillGapSettings
from .assets import ASSET_ROOT
from .core_cards import CoreSkillCards
from .skill_groups import GROUP_SKILLS, PARTITION_POLICY_VERSION, build_group_format
from .sources import build_index
from .transport import SkillGapConfigurationError, create_response


GROUPS = ("foundation", "lifecycle", "systems")
GROUP_TRANSPORT_VERSION = "core-skill-evidence-transport.v1"
GROUP_SCHEMA_NAME = "careergps_core_skill_groups_v12"
_CONTRACT_ROOT = BACKEND_ROOT / "app" / "prompts" / "skill_gaps" / "skill_groups"
GROUP_INSTRUCTIONS_PATHS = {
    group: _CONTRACT_ROOT / group / "Instructions.md" for group in GROUPS
}
GROUP_FORMAT_PATHS = {
    group: _CONTRACT_ROOT / group / "response-format.json" for group in GROUPS
}
_CATALOG_PATH = ASSET_ROOT / "core_catalog.json"


_SAVED_VERSION = re.compile(r"[1-9][0-9]*\Z")


@dataclass(frozen=True)
class PreparedGroup:
    branch: str
    project_endpoint: str
    agent_name: str
    agent_version: str
    definition: dict
    configuration_check: dict


def _text(value) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def _latest(value) -> bool:
    return value is None or (isinstance(value, str)
                            and (not value.strip() or value.strip().casefold() == "latest"))


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _field(value, name: str):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _definition(value) -> dict:
    if isinstance(value, dict):
        return deepcopy(value)
    as_dict = getattr(value, "as_dict", None)
    result = as_dict() if callable(as_dict) else {}
    return deepcopy(result) if isinstance(result, dict) else {}


def _fail(group: str, code: str, detail: str, save: Callable | None = None,
          check: dict | None = None) -> None:
    code = f"{group}_{code}"
    if save is not None:
        save(group, "configuration_check.json", {
            "branch": group, "model_calls": 0,
            **(check or {}), "configuration_error_code": code,
        })
    raise SkillGapConfigurationError(code, f"Skill Gap {group} group: {detail}") from None


def _groups(groups: Iterable[str]) -> tuple[str, ...]:
    if isinstance(groups, str):
        raise SkillGapConfigurationError("group_scope_invalid", "Choose foundation, lifecycle or systems groups.")
    requested = []
    for group in groups:
        if not isinstance(group, str) or group not in GROUPS:
            raise SkillGapConfigurationError("group_scope_invalid", "Choose foundation, lifecycle or systems groups.")
        if group not in requested:
            requested.append(group)
    return tuple(requested)


def uses_latest(settings: SkillGapSettings) -> bool:
    return any(_latest(getattr(settings, f"skill_gap_{group}_agent_version", None))
               for group in GROUPS)


def configuration_signature(settings: SkillGapSettings) -> dict:
    """Local fingerprints include the approved prompt and each internal Schema.

    Latest discovery still checks cloud Instructions against the local approved
    experiment. A newly saved, different prompt requires an explicit local sync.
    Missing or broken contracts are represented here and rejected at preflight.
    """
    bindings, schemas, schema_files = {}, {}, {}
    for group in GROUPS:
        format_path = GROUP_FORMAT_PATHS[group]
        try:
            format_bytes = format_path.read_bytes()
            format_ = json.loads(format_bytes)
            schema_hash = _digest(format_["schema"])
            schema_name = format_["name"]
            schema_file_hash = hashlib.sha256(format_bytes).hexdigest()
        except (OSError, ValueError, TypeError, KeyError):
            schema_hash = schema_name = schema_file_hash = None
        configured = getattr(settings, f"skill_gap_{group}_agent_version", None)
        bindings[group] = {
            "agent_name": _text(getattr(settings, f"skill_gap_{group}_agent_name", None)),
            "agent_version": "latest" if _latest(configured) else _text(configured),
            "instructions_sha256": _file_digest(GROUP_INSTRUCTIONS_PATHS[group]),
            "instructions_source": "local_approved_cloud_saved",
            "schema_name": schema_name,
            "schema_sha256": schema_hash,
            "schema_file_sha256": schema_file_hash,
        }
        schemas[group], schema_files[group] = schema_hash, schema_file_hash
    return {
        "transport_version": GROUP_TRANSPORT_VERSION,
        "strategy": "skill_groups",
        "project_endpoint": _text(getattr(settings, "skill_gap_foundry_project_endpoint", None)),
        "branches": bindings,
        "schema_name": GROUP_SCHEMA_NAME,
        "schema_sha256": _digest(schemas),
        "schema_file_sha256": _digest(schema_files),
        "catalog_sha256": _file_digest(_CATALOG_PATH),
        "partition_policy_version": PARTITION_POLICY_VERSION,
    }


def resolved_configuration_signature(settings: SkillGapSettings,
                                     prepared: dict[str, PreparedGroup]) -> dict:
    signature = configuration_signature(settings)
    for group, value in prepared.items():
        if group not in GROUPS or value.branch != group:
            raise SkillGapConfigurationError("group_scope_invalid", "Choose foundation, lifecycle or systems groups.")
        signature["branches"][group].update(
            agent_name=value.agent_name, agent_version=value.agent_version,
            definition_sha256=_digest(value.definition),
            observed_instructions_sha256=hashlib.sha256(
                value.definition.get("instructions", "").encode("utf-8")).hexdigest(),
        )
    return signature


def _load_local_contract(group: str, save: Callable | None = None) -> tuple[str, dict, str, str, dict]:
    try:
        instructions_bytes = GROUP_INSTRUCTIONS_PATHS[group].read_bytes()
        format_bytes = GROUP_FORMAT_PATHS[group].read_bytes()
        catalog = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        instructions = instructions_bytes.decode("utf-8")
        format_ = json.loads(format_bytes)
        if not instructions.strip() or format_ != build_group_format(catalog, group):
            raise ValueError("The approved group contract differs from its generated catalog Schema")
        return (instructions, format_, hashlib.sha256(instructions_bytes).hexdigest(),
                hashlib.sha256(format_bytes).hexdigest(), catalog)
    except (OSError, ValueError, TypeError, KeyError):
        _fail(group, "local_contract_unavailable",
              "Restore this group's approved Instructions and generated internal Schema before retrying. No model call was made.", save)


def _check_definition(group: str, definition: dict, version: str, instructions: str,
                      expected_format: dict, save: Callable, *, instructions_hash: str,
                      schema_file_hash: str) -> dict:
    observed = definition.get("instructions")
    observed = observed if isinstance(observed, str) else ""
    expected_text, observed_text = " ".join(instructions.split()), " ".join(observed.split())
    text = definition.get("text")
    format_ = text.get("format") if isinstance(text, dict) else {}
    format_ = format_ if isinstance(format_, dict) else {}
    schema = format_.get("schema") if "schema" in format_ else format_.get("schema_")
    reasoning = definition.get("reasoning")
    effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
    check = {
        "branch": group, "agent_version": version, "pinned_version_match": True,
        "transport_version": GROUP_TRANSPORT_VERSION,
        "instructions_match": bool(observed_text) and observed_text == expected_text,
        "instructions_source": "foundry",
        "instructions_match_scope": "local_approved_contract_including_latest_selection",
        "expected_instructions_sha256": _digest(expected_text),
        "observed_instructions_sha256": _digest(observed_text),
        "observed_instructions_raw_sha256": hashlib.sha256(observed.encode("utf-8")).hexdigest(),
        "definition_sha256": _digest(definition),
        "schema_match": (format_.get("type") == "json_schema"
                         and format_.get("name") == expected_format["name"]
                         and format_.get("strict") is True and schema == expected_format["schema"]),
        "schema_name": expected_format["name"],
        "expected_schema_sha256": _digest(expected_format["schema"]),
        "observed_schema_sha256": _digest(schema),
        "instructions_file_sha256": instructions_hash,
        "schema_file_sha256": schema_file_hash,
        "catalog_file_sha256": _file_digest(_CATALOG_PATH),
        "reasoning_effort": effort, "reasoning_match": effort == "medium", "model_calls": 0,
    }
    save(group, "configuration_check.json", check)
    if not check["schema_match"]:
        _fail(group, "schema_mismatch",
              "Synchronize the saved Agent with this group's generated internal Schema. No model call was made.", save, check)
    if not check["instructions_match"]:
        _fail(group, "instructions_mismatch",
              "Synchronize the saved Agent with this group's approved Instructions before retrying. No model call was made.", save, check)
    if not check["reasoning_match"]:
        _fail(group, "reasoning_mismatch",
              "Use medium reasoning for this controlled skill-group experiment. No model call was made.", save, check)
    return check


def preflight(branches: Iterable[str], save: Callable, *, settings: SkillGapSettings) -> dict[str, PreparedGroup]:
    """Check every active group before any inference; latest resolves to a pin."""
    requested = _groups(branches)
    if not requested:
        return {}
    endpoint = _text(getattr(settings, "skill_gap_foundry_project_endpoint", None))
    local = {}
    for group in requested:
        name = _text(getattr(settings, f"skill_gap_{group}_agent_name", None))
        configured = getattr(settings, f"skill_gap_{group}_agent_version", None)
        latest = _latest(configured)
        version = "latest" if latest else _text(configured)
        if not endpoint or not name:
            _fail(group, "agent_not_configured",
                  "Set the shared project endpoint and this skill group's Agent name before retrying.", save)
        if not latest and (not version or not _SAVED_VERSION.fullmatch(version)):
            _fail(group, "agent_version_unavailable",
                  "Choose latest or a saved positive-integer Agent version; draft versions are not accepted.", save)
        local[group] = (name, version, latest, _load_local_contract(group, save))

    group = requested[0]
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        prepared = {}
        with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
            with AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project:
                for group in requested:
                    name, version, latest, contract = local[group]
                    if latest:
                        saved = next(iter(project.agents.list_versions(
                            name, limit=1, order="desc", include_drafts=False)), None)
                        if saved is None:
                            _fail(group, "agent_version_unavailable",
                                  "No saved non-draft version is available for this skill group. No model call was made.", save)
                    else:
                        saved = project.agents.get_version(name, version)
                    observed_version, observed_name = _field(saved, "version"), _field(saved, "name")
                    draft = _field(saved, "draft")
                    if draft is None:
                        draft = _field(saved, "is_draft")
                    if (observed_version is None or not _SAVED_VERSION.fullmatch(str(observed_version))
                            or (not latest and str(observed_version) != version)):
                        _fail(group, "agent_version_mismatch", "The returned saved version does not match the requested binding.", save)
                    if observed_name is not None and observed_name != name:
                        _fail(group, "agent_name_mismatch", "The saved Agent name does not match this skill group.", save)
                    if draft is True:
                        _fail(group, "agent_draft", "Save a non-draft version before retrying. No model call was made.", save)
                    definition = _definition(_field(saved, "definition"))
                    version = str(observed_version)
                    save(group, "observed_agent.json", {
                        "branch": group, "name": name, "version": version, "draft": draft,
                        "definition": definition, "instructions_source": "foundry",
                    })
                    instructions, format_, instructions_hash, schema_file_hash, _ = contract
                    check = _check_definition(group, definition, version, instructions, format_, save,
                                              instructions_hash=instructions_hash, schema_file_hash=schema_file_hash)
                    prepared[group] = PreparedGroup(group, endpoint, name, version, definition, check)
        return prepared
    except SkillGapConfigurationError:
        raise
    except Exception:
        _fail(group, "agent_unavailable",
              "Could not read or validate this skill group's saved Agent. Check the binding and Azure access. No model call was made.", save)


def _validate_scope(group: str, payload: dict, catalog: dict) -> None:
    try:
        scope = payload["evidence_scope"]
        family = payload["job_family"]
        assigned = set(GROUP_SKILLS[family][group])
        cards = [card for card in CoreSkillCards(catalog).for_family(family)
                 if card["skill_id"] in assigned]
        expected_ids = [card["skill_id"] for card in cards]
        sources = payload["resume_sources"]
        if (payload.get("task") != "extract_resume_evidence"
                or scope.get("branch") != group
                or scope.get("partition_policy_version") != PARTITION_POLICY_VERSION
                or scope.get("assigned_skill_ids") != expected_ids
                or payload.get("core_skills") != cards
                or scope.get("activity_ids") != [source["id"] for source in sources]
                or any(not isinstance(source.get("path"), str)
                       or not source["path"].startswith("/")
                       or source["path"].split("/", 2)[1] == "personal_information" for source in sources)):
            raise ValueError("Group assignment or source scope differs")
        build_index(sources)
    except (ValueError, TypeError, KeyError, AttributeError):
        _fail(group, "scope_mismatch",
              "The input does not match this group's assigned catalog skills and original source scope. Rebuild the run input before retrying.")


def _decode_response(response, save: Callable, expected_name: str) -> dict:
    raw = response.model_dump(mode="json")
    save("agent.raw.json", raw)
    if response.status != "completed":
        raise RuntimeError("Agent response incomplete; raw response saved, no automatic retry")
    format_ = (raw.get("text") or {}).get("format") or {}
    if (format_.get("type") != "json_schema" or format_.get("strict") is not True
            or format_.get("name") != expected_name):
        raise RuntimeError("The response did not use the checked internal group format")
    return json.loads(response.output_text)


def invoke_prepared(prepared: PreparedGroup, payload: dict, save: Callable,
                    on_request: Callable, timings: dict) -> dict:
    group = prepared.branch
    if group not in GROUPS:
        raise SkillGapConfigurationError("group_scope_invalid", "Choose foundation, lifecycle or systems groups.")
    instructions, format_, instructions_hash, schema_file_hash, catalog = _load_local_contract(group)
    _validate_scope(group, payload, catalog)
    check = prepared.configuration_check
    if (instructions_hash != check.get("instructions_file_sha256")
            or schema_file_hash != check.get("schema_file_sha256")
            or _file_digest(_CATALOG_PATH) != check.get("catalog_file_sha256")):
        _fail(group, "local_contract_changed",
              "The approved prompt, catalog or internal Schema changed after preflight. Start a new analysis. No model call was made.")
    if _digest(prepared.definition) != check.get("definition_sha256"):
        _fail(group, "prepared_configuration_changed",
              "The checked Agent snapshot changed in memory. Start a new analysis. No model call was made.")
    started = time.perf_counter()
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
            with AIProjectClient(endpoint=prepared.project_endpoint, credential=credential, allow_preview=True) as project:
                with project.get_openai_client(timeout=480, max_retries=0) as client:
                    timings["sdk_auth_configuration_seconds"] = round(time.perf_counter() - started, 3)
                    response = create_response(client, payload, on_request, timings, agent_reference={
                        "type": "agent_reference", "name": prepared.agent_name, "version": prepared.agent_version,
                    })
        return _decode_response(response, save, format_["name"])
    except SkillGapConfigurationError:
        raise
    except Exception:
        _fail(group, "inference_failed",
              "The saved skill-group request could not finish or returned an incompatible response. Check its saved artifacts before explicitly retrying; no automatic retry was made.")
