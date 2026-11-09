"""Agent callers for the gpt-6 configs. Each has the same signature as transport.invoke:

    invoke(payload, save, on_request, timings) -> v12 agent output

A6: one pinned single-Agent call (olive-agent v31), checked against a local copy of
    that version's own prompt, because v31's prompt is not the app's Instructions.md.
C6: the three skill-group Agents, using the app's own preflight, split, call and
    merge from the 3-skill-gap-agents work. All three run in parallel with no cache.

Both save `usage.json` (summed token counts) and `observed_agent.json` so the runner
records them the same way as config A.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from app.core.config import SkillGapSettings
from app.services.skill_gaps.storage import load
from app.services.skill_gaps.assets import ASSET_ROOT
from app.services.skill_gaps.transport import (
    SkillGapConfigurationError, create_response, decode_response, load_local_contract,
)

PROMPTS = Path(__file__).resolve().parent / "prompts"
SINGLE_GPT6 = {"version": "31", "instructions": PROMPTS / "olive_v31.md"}
TOKEN_FIELDS = ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")


def usage_of(raw):
    usage = (raw or {}).get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "cached_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
    }


def _same_text(a, b):
    return " ".join((a or "").split()) == " ".join((b or "").split())


def invoke_single_pinned(payload, save, on_request, timings, *, settings=None,
                         version=SINGLE_GPT6["version"], instructions_path=SINGLE_GPT6["instructions"]):
    """A6: the configured single Agent at a fixed version, with its own saved prompt."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    started = time.perf_counter()
    settings = settings or SkillGapSettings()
    name = settings.skill_gap_foundry_agent_name
    if not settings.skill_gap_foundry_project_endpoint or not name:
        raise SkillGapConfigurationError("agent_not_configured", "Set the Skill Gap endpoint and single Agent name.")
    _, expected_format = load_local_contract()
    instructions = instructions_path.read_text(encoding="utf-8")
    with DefaultAzureCredential(exclude_managed_identity_credential=True) as credential:
        with AIProjectClient(endpoint=settings.skill_gap_foundry_project_endpoint,
                             credential=credential, allow_preview=True) as project:
            definition = project.agents.get_version(name, version).definition.as_dict()
            text_format = (definition.get("text") or {}).get("format") or {}
            check = {
                "agent_version": version, "instructions_file": instructions_path.name,
                "instructions_match": _same_text(definition.get("instructions"), instructions),
                "schema_match": (text_format.get("schema") or text_format.get("schema_")) == expected_format["schema"],
            }
            save("configuration_check.json", check)
            if not (check["instructions_match"] and check["schema_match"]):
                raise SkillGapConfigurationError("definition_mismatch",
                    f"{name} v{version} differs from {instructions_path.name} or the v12 schema. No model call was made.")
            save("observed_agent.json", {"name": name, "version": version, "definition": definition})
            with project.get_openai_client(timeout=480, max_retries=0) as client:
                timings["sdk_auth_configuration_seconds"] = round(time.perf_counter() - started, 3)
                response = create_response(client, payload, on_request, timings,
                    agent_reference={"type": "agent_reference", "name": name, "version": version})
    output = decode_response(response, save)
    save("usage.json", usage_of(response.model_dump(mode="json")))
    return output


def invoke_groups(payload, save, on_request, timings, *, settings=None, preflight=None,
                  invoke_group=None, merge=None, catalog=None):
    """C6: preflight all three groups, call them in parallel, merge each owner's skills."""
    from app.services.skill_gaps import skill_group_transport as transport
    from app.services.skill_gaps.skill_groups import GROUPS, make_group_payloads, merge_group_outputs

    preflight = preflight or transport.preflight
    invoke_group = invoke_group or transport.invoke_prepared
    merge = merge or merge_group_outputs
    catalog = catalog or load(ASSET_ROOT / "core_catalog.json")
    settings = settings or SkillGapSettings()

    started = time.perf_counter()
    prepared = preflight(GROUPS, lambda group, name, value: save(f"{group}.{name}", value), settings=settings)
    timings["sdk_auth_configuration_seconds"] = round(time.perf_counter() - started, 3)
    payloads = make_group_payloads(payload)
    for group in GROUPS:
        save(f"{group}.input.json", payloads[group])

    raws, group_timings = {}, {group: {} for group in GROUPS}

    def call(group):
        def save_group(name, value):
            if name == "agent.raw.json":
                raws[group] = value
            save(f"{group}.{name}", value)
        begun = time.perf_counter()
        try:
            return invoke_group(prepared[group], payloads[group], save_group, on_request, group_timings[group])
        finally:
            group_timings[group]["wall_seconds"] = round(time.perf_counter() - begun, 3)

    started = time.perf_counter()
    outputs, errors = {}, {}
    with ThreadPoolExecutor(max_workers=len(GROUPS), thread_name_prefix="experiment-group") as pool:
        futures = {group: pool.submit(call, group) for group in GROUPS}
        for group, future in futures.items():
            try:
                outputs[group] = future.result()
            except Exception as error:  # every group finishes before the run is marked failed
                errors[group] = f"{type(error).__name__}: {error}"
    timings["inference_seconds"] = round(time.perf_counter() - started, 3)
    timings["groups"] = group_timings

    per_group = {group: usage_of(raws.get(group)) for group in GROUPS}
    first = next((raw for raw in raws.values() if raw), {}) or {}
    save("usage.json", {**{field: _total(item.get(field) for item in per_group.values()) for field in TOKEN_FIELDS},
                        "groups": per_group})
    save("observed_agent.json", {
        "name": "+".join(prepared[group].agent_name for group in GROUPS),
        "version": "/".join(prepared[group].agent_version for group in GROUPS),
        "definition": {"model": first.get("model") or prepared[GROUPS[0]].definition.get("model"),
                       "reasoning": first.get("reasoning") or prepared[GROUPS[0]].definition.get("reasoning")},
    })
    for group in GROUPS:
        output = outputs.get(group)
        if output is not None:
            save(f"{group}.agent.response.json", output)
    if errors:
        raise RuntimeError("; ".join(f"{group}: {message}" for group, message in errors.items()))

    merged, audit = merge(payload["job_family"], outputs, catalog, payload["resume_sources"])
    save("group_merge_audit.json", audit)
    return merged


def _total(values):
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def review_blocked(audit):
    """Skills the merge turned into uncertain because the owner's evidence failed its checks."""
    skills = (audit or {}).get("skills") or {}
    return sum(1 for item in skills.values() if item.get("reason") == "assigned_owner_requires_review")


def group_summary(timings, usage):
    groups = (timings or {}).get("groups") or {}
    tokens = (usage or {}).get("groups") or {}
    if not groups:
        return {}
    walls = {group: item.get("wall_seconds") for group, item in groups.items()}
    slowest = max((group for group in walls if walls[group] is not None), key=walls.get, default=None)
    return {
        "group_inference_s": json.dumps({group: item.get("inference_seconds") for group, item in groups.items()},
                                        separators=(",", ":")),
        "group_output_tokens": json.dumps({group: (tokens.get(group) or {}).get("output_tokens") for group in groups},
                                          separators=(",", ":")),
        "slowest_group": slowest,
    }
