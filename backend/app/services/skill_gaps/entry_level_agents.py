"""Load and verify the reproducible, reviewed nine-Agent production bundle."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from app.core.config import BACKEND_ROOT
from .entry_level import build_format
from .skill_groups import GROUPS


BUNDLE_ROOT = BACKEND_ROOT / "app" / "prompts" / "skill_gaps" / "entry_level"
BUNDLE_VERSION = "careergps-entry-level-agents.v1"
MODEL = "gpt-6-luna"
REASONING_EFFORT = "medium"
FAMILY_SLUGS = {"ai_engineer": "ai", "software_engineer": "se", "data_analyst": "da"}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class AgentBundleError(ValueError):
    """An artifact or remote Agent differs from the reviewed configuration."""


def digest(value: object) -> str:
    """Use the same canonical definition hash as the production transport."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AgentDefinition:
    family: str
    group: str
    name: str
    version: str
    instructions_sha256: str
    response_format_sha256: str
    definition_sha256: str
    instructions_path: Path
    response_format_path: Path
    source_name: str
    source_version: str
    definition: dict


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise AgentBundleError(f"{label} has missing or unexpected fields")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AgentBundleError("JSON contains a duplicate object key")
        result[key] = value
    return result


def _json_file(path):
    try:
        return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AgentBundleError(f"Cannot read valid JSON from {path.name}") from exc


def _artifact(root, relative):
    if not isinstance(relative, str) or not relative:
        raise AgentBundleError("Artifact paths must be nonempty relative strings")
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive:
        raise AgentBundleError("Artifact paths must stay inside the bundle")
    path = (root / candidate).resolve()
    if not path.is_relative_to(root):
        raise AgentBundleError("Artifact paths must stay inside the bundle")
    if not path.is_file():
        raise AgentBundleError(f"Missing Agent artifact: {relative}")
    return path


def load_bundle(root: Path = BUNDLE_ROOT) -> dict[tuple[str, str], AgentDefinition]:
    """Validate all nine definitions locally; no Azure imports or calls."""
    root = Path(root).resolve()
    manifest = _json_file(root / "manifest.json")
    _fields(manifest, ("bundle_version", "model", "reasoning_effort", "agents"), "Manifest")
    if (manifest["bundle_version"], manifest["model"], manifest["reasoning_effort"]) != (
        BUNDLE_VERSION, MODEL, REASONING_EFFORT
    ):
        raise AgentBundleError("Bundle version, model or reasoning differs from the reviewed policy")
    _fields(manifest["agents"], FAMILY_SLUGS, "Agent families")
    result = {}
    for family, slug in FAMILY_SLUGS.items():
        groups = manifest["agents"][family]
        _fields(groups, GROUPS, f"{family} groups")
        for group in GROUPS:
            label = f"{family}/{group}"
            item = groups[group]
            _fields(item, ("name", "version", "instructions", "response_format", "instructions_sha256",
                           "response_format_sha256", "definition_sha256", "definition_options", "source"), label)
            if item["name"] != f"careergps-entry-level-{slug}-{group}" or item["version"] != "1":
                raise AgentBundleError(f"{label} must use its production name and pinned version 1")
            for field in ("instructions_sha256", "response_format_sha256", "definition_sha256"):
                if not isinstance(item[field], str) or not _HASH.fullmatch(item[field]):
                    raise AgentBundleError(f"{label} has an invalid {field}")
            source = item["source"]
            _fields(source, ("name", "version", "definition_sha256"), f"{label} source")
            if (not isinstance(source["name"], str) or not source["name"]
                    or not isinstance(source["version"], str) or not re.fullmatch(r"[1-9][0-9]*", source["version"])
                    or source["definition_sha256"] != item["definition_sha256"]):
                raise AgentBundleError(f"{label} source provenance differs from the exact definition")
            instructions_path = _artifact(root, item["instructions"])
            format_path = _artifact(root, item["response_format"])
            try:
                instructions_bytes = instructions_path.read_bytes()
                instructions = instructions_bytes.decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise AgentBundleError(f"{label} instructions must be readable UTF-8") from exc
            if not instructions.strip() or hashlib.sha256(instructions_bytes).hexdigest() != item["instructions_sha256"]:
                raise AgentBundleError(f"{label} instructions hash mismatch")
            response_format = _json_file(format_path)
            if digest(response_format) != item["response_format_sha256"]:
                raise AgentBundleError(f"{label} response format hash mismatch")
            if response_format != {"type": "json_schema", **build_format(group, family)}:
                raise AgentBundleError(f"{label} response format differs from the production schema")
            options = item["definition_options"]
            if (not isinstance(options, dict) or "instructions" in options
                    or not isinstance(options.get("text"), dict) or "format" in options["text"]):
                raise AgentBundleError(f"{label} definition options must leave instructions and format to artifacts")
            definition = deepcopy(options)
            definition["instructions"] = instructions
            definition["text"]["format"] = response_format
            if (definition.get("kind") != "prompt" or definition.get("model") != MODEL
                    or definition.get("reasoning") != {"effort": REASONING_EFFORT}
                    or definition.get("tools") != []):
                raise AgentBundleError(f"{label} model, reasoning or tools differs from the reviewed policy")
            if digest(definition) != item["definition_sha256"]:
                raise AgentBundleError(f"{label} complete definition hash mismatch")
            result[family, group] = AgentDefinition(
                family, group, item["name"], item["version"], item["instructions_sha256"],
                item["response_format_sha256"], item["definition_sha256"], instructions_path, format_path,
                source["name"], source["version"], definition,
            )
    return result


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def verify_saved_agent(saved, expected: AgentDefinition) -> None:
    """Check immutable identity and the complete definition returned by Foundry."""
    definition = _field(saved, "definition")
    if not isinstance(definition, dict):
        converter = getattr(definition, "as_dict", None)
        definition = converter() if callable(converter) else None
    if (_field(saved, "name") not in (None, expected.name)
            or str(_field(saved, "version")) != expected.version
            or _field(saved, "draft") is True or _field(saved, "is_draft") is True
            or not isinstance(definition, dict) or digest(definition) != expected.definition_sha256):
        raise AgentBundleError(f"Saved Agent {expected.name} v{expected.version} differs from the reviewed bundle")


def manage_agents(client, bundle: dict[tuple[str, str], AgentDefinition], *, create: bool = False) -> list[dict]:
    """Verify every existing pin before creating missing names; never update or delete.

    A repeated create reuses an identical pinned version. An existing name with
    no approved version is a conflict, rather than permission to add a version.
    """
    from azure.core.exceptions import ResourceNotFoundError

    for expected in bundle.values():
        if digest(expected.definition) != expected.definition_sha256:
            raise AgentBundleError(f"Local definition {expected.name} changed after bundle validation")
    missing = []
    results = []
    for expected in bundle.values():
        try:
            saved = client.agents.get_version(expected.name, expected.version)
        except ResourceNotFoundError:
            if not create:
                raise AgentBundleError(f"Missing Agent {expected.name} v{expected.version}") from None
            try:
                client.agents.get(expected.name)
            except ResourceNotFoundError:
                missing.append(expected)
            else:
                raise AgentBundleError(f"Agent name {expected.name} already exists without its approved version") from None
        else:
            verify_saved_agent(saved, expected)
            results.append({"family": expected.family, "group": expected.group, "name": expected.name,
                            "version": expected.version, "action": "verified"})
    for expected in missing:
        saved = client.agents.create_version(expected.name, body={
            "definition": deepcopy(expected.definition),
            "description": f"CareerGPS entry-level {expected.family} {expected.group} evidence assessment.",
            "metadata": {"scope": "careergps-production", "bundle_version": BUNDLE_VERSION},
        })
        verify_saved_agent(saved, expected)
        # Read back the immutable pin before reporting successful creation.
        verify_saved_agent(client.agents.get_version(expected.name, expected.version), expected)
        results.append({"family": expected.family, "group": expected.group, "name": expected.name,
                        "version": expected.version, "action": "created"})
    return results
