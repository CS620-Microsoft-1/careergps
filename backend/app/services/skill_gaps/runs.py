"""Owner-scoped, single-worker analysis using detached database resume snapshots.

Results remain local JSON. Workers never retain a request's ORM session, and
polling/restoring never starts a model call.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from threading import Lock, RLock
import time
from typing import Callable
from uuid import UUID, uuid4

from app.core.config import BACKEND_ROOT, SkillGapSettings
from app.schemas.skill_gap_web import JobFamily, SkillGapRun
from .response import RESPONSE_PROCESSING_VERSION, calculate_web_report
from .transport import SkillGapConfigurationError
from .scoring import POLICY_VERSION
from .assets import ASSET_ROOT
from .input import prepare
from .core_cards import CoreSkillCards
from .branch_cache import BRANCH_CACHE_VERSION, BranchCache
from .match import summarize_match
from .storage import load, save_json
from .schema import SCHEMA_NAME
from .skill_groups import (
    GROUPS, PARTITION_POLICY_VERSION, SELECTION_POLICY_VERSION,
    absent_output, make_group_payloads, merge_group_outputs, validate_group_output,
)
from .skill_group_transport import (
    configuration_signature, invoke_prepared, preflight,
    resolved_configuration_signature, uses_latest,
)

_ID = re.compile(r"[0-9a-f]{32}\Z")
_ARTIFACTS = {"input.json", "reviewed_resume.json", "observed_agent.json", "agent.raw.json",
              "agent.response.json", "local_checks.json", "coverage_audit.json", "skill_gaps.json",
              "response_processing.json", "configuration_check.json", "extraction_audit.json",
              "cache_provenance.json", "source_agent.raw.json"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class SkillGapRunManager:
    def __init__(self, directory: Path | None = None, *, settings: SkillGapSettings | None = None,
                 group_invoker: Callable | None = None, group_preflight: Callable | None = None,
                 invoker: Callable | None = None) -> None:
        self.directory = (directory or BACKEND_ROOT / "local_results" / "web_skill_gaps").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.settings = (settings or SkillGapSettings()).model_copy(deep=True)
        self._branches = GROUPS
        self._partition_policy = PARTITION_POLICY_VERSION
        self._selection_policy = SELECTION_POLICY_VERSION
        self._make_branch_payloads = make_group_payloads
        self._merge_outputs = merge_group_outputs
        self._configuration_signature = lambda settings: configuration_signature(settings)
        self._resolved_configuration_signature = resolved_configuration_signature
        if group_invoker is not None and invoker is not None:
            raise ValueError("Choose one injected group invoker")
        # The legacy test hook is adapted to each group; production always uses
        # the checked saved group transport, never the former single Agent.
        if group_invoker is not None:
            self._branch_invoke = group_invoker
        elif invoker is not None:
            self._branch_invoke = lambda prepared, payload, save, on_request, timings: invoker(
                payload, save, on_request, timings)
        else:
            self._branch_invoke = invoke_prepared
        self._branch_preflight = group_preflight or preflight
        self.branch_signature = configuration_signature(self.settings)
        self._latest_versions = uses_latest(self.settings)
        self._prepared_runs: dict[str, dict] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-skill-gap")
        self._states: dict[str, dict] = {}
        self._keys: dict[str, str] = {}
        self.catalog = load(ASSET_ROOT / "core_catalog.json")
        self.market = load(ASSET_ROOT / "market_snapshot.json")
        self.core_cards = CoreSkillCards(self.catalog)
        self.branch_cache = BranchCache(self.directory / "_branch_cache")
        self.instructions_sha256 = _sha({
            group: self.branch_signature["branches"][group]["instructions_sha256"]
            for group in self._branches})
        self.prompt_revision = "skill-groups.v1"
        fingerprint = {"response_processing": RESPONSE_PROCESSING_VERSION,
            "core_cards": self.core_cards.signature(), "web_instructions": self.instructions_sha256,
            "v12_assets": {name: hashlib.sha256((ASSET_ROOT / name).read_bytes()).hexdigest()
                for name in ("core_catalog.json", "market_snapshot.json", "scoring_policy.json", "response-format.json")},
            "extraction_strategy": "skill_groups", "branch_configuration": self.branch_signature,
            "partition_policy": self._partition_policy, "selection_policy": self._selection_policy,
            "branch_cache_version": BRANCH_CACHE_VERSION}
        self._fingerprint_material = fingerprint
        self.fingerprint = _sha(fingerprint)
        self._recover()

    def _folder(self, identifier: str) -> Path:
        if not _ID.fullmatch(identifier):
            raise KeyError(identifier)
        return self.directory / identifier

    def _persist(self, state: dict) -> None:
        folder = self._folder(state["id"])
        save_json(folder / "status.json", state)
        save_json(folder / "run.json", {
            "mode": "authenticated_web", "status": state["status"], "phase": state["phase"],
            "user_id": state["user_id"], "resume_id": state["resume_id"],
            "resume_source": "resumes.confirmed_data", "result_storage": "local_json",
            "job_family": state["job_family"], "resume_hash": state["resume_hash"],
            "policy_version": POLICY_VERSION, "expected_schema_name": SCHEMA_NAME,
            "calculation_fingerprint": state["calculation_fingerprint"],
            "prompt_revision": state.get("prompt_revision"),
            "instructions_sha256": state.get("instructions_sha256"),
            "error_code": state.get("error_code"),
            "response_processing_version": state.get("response_processing_version"),
            "extraction_strategy": state.get("extraction_strategy", "single"),
            "branches": state.get("branches", {}),
            "branch_configuration": state.get("branch_configuration"),
            "version_selection": state.get("version_selection", "pinned"),
            "reuse_from_run_id": state.get("reuse_from_run_id"),
            "branch_cache_policy": state.get("branch_cache_policy"),
            "rebuild_report": state.get("rebuild_report", False),
            "core_skill_cards": state.get("core_skill_cards"),
            "local_reprocessing": state.get("local_reprocessing"),
            "model_calls": state["model_calls"], "repair_calls": 0, "summary_calls": 0,
            "created_at": state["created_at"], "completed_at": state["completed_at"],
            "elapsed_seconds": state["elapsed_seconds"],
            "azure_phase_timings": state.get("azure_phase_timings", {}),
        })

    def _recover(self) -> None:
        # Interrupted tasks are never retried implicitly. A manual force request
        # is required; a prior request may already have reached the model.
        for path in sorted(self.directory.glob("*/status.json")):
            if not _ID.fullmatch(path.parent.name):
                continue
            try:
                state = load(path)
                if state["id"] != path.parent.name:
                    continue
                # Ownerless pre-auth experiments are preserved on disk, never
                # adopted by an account or exposed through the authenticated API.
                for name in ("user_id", "resume_id"):
                    state[name] = str(UUID(state[name]))
                expected = self._cache_key(state["user_id"], state["resume_id"], state["resume_hash"],
                                           state["job_family"], state["calculation_fingerprint"])
                if state["cache_key"] != expected:
                    continue
                created = datetime.fromisoformat(state["created_at"])
                if created.tzinfo is None:
                    continue
                self._view(state)  # Validate fields before trusting a local record.
                if state["status"] in ("queued", "running"):
                    state.update(status="failed", phase="failed", completed_at=_now(),
                                 error="The previous analysis process stopped. Start a new analysis explicitly.")
                    self._persist(state)
                self._states[state["id"]] = state
                prior = self._states.get(self._keys.get(state["cache_key"], ""))
                if prior is None or (created, state["id"]) > (
                        datetime.fromisoformat(prior["created_at"]), prior["id"]):
                    self._keys[state["cache_key"]] = state["id"]
            except (OSError, ValueError, TypeError, KeyError):
                continue

    def _view(self, state: dict, *, reused: bool = False) -> SkillGapRun:
        keys = ("id", "user_id", "resume_id", "status", "phase", "job_family", "filename", "resume_hash", "created_at",
                "completed_at", "elapsed_seconds", "model_calls", "error")
        value = {key: deepcopy(state[key]) for key in keys}
        if state["status"] in ("queued", "running"):
            value["elapsed_seconds"] = round(max(0, (datetime.now(timezone.utc) -
                                                    datetime.fromisoformat(state["created_at"])).total_seconds()), 3)
        value["report"] = load(self._folder(state["id"]) / "skill_gaps.json") if state["status"] == "completed" else None
        value["reused"] = reused
        value["match"] = summarize_match(value["report"])
        return SkillGapRun.model_validate(value)

    def _cache_key(self, user_id: str, resume_id: str, resume_hash: str,
                   job_family: JobFamily, fingerprint: str | None = None) -> str:
        return _sha({"user_id": user_id, "resume_id": resume_id, "resume_hash": resume_hash,
                     "job_family": job_family, "contract": SCHEMA_NAME,
                     "fingerprint": fingerprint or self.fingerprint})

    def _resolve_latest(self, reviewed: dict, resume_id: str, job_family: JobFamily) -> tuple:
        """Resolve saved definitions before any cache lookup, without inference.

        The returned configuration belongs to this request, never to the shared
        manager. Another queued request may resolve a different set of versions.
        """
        if self._configuration_signature(self.settings) != self.branch_signature:
            raise SkillGapConfigurationError("local_instructions_changed",
                "The local Skill Gap contract changed. Restart the API before a new analysis.")
        payload = prepare(job_family, reviewed, resume_id, self.catalog, core_cards=self.core_cards)
        payloads = self._make_branch_payloads(payload)
        active = [branch for branch in self._branches
                  if any(source["units"] for source in payloads[branch]["resume_sources"])]
        artifacts = {}

        def collect(branch: str, name: str, value: object) -> None:
            if branch not in active or name not in _ARTIFACTS:
                raise ValueError("Unexpected configuration artifact")
            artifacts[branch, name] = deepcopy(value)

        prepared = self._branch_preflight(active, collect, settings=self.settings) if active else {}
        if set(prepared) != set(active):
            raise SkillGapConfigurationError("incomplete_branch_configuration",
                "All active evidence Agents must pass configuration checks before analysis can start.")
        if self._configuration_signature(self.settings) != self.branch_signature:
            raise SkillGapConfigurationError("local_instructions_changed",
                "The local Skill Gap contract changed during version lookup. Retry after restarting the API.")
        signature = self._resolved_configuration_signature(self.settings, prepared)
        instruction_hash = _sha({branch: signature["branches"][branch]["instructions_sha256"]
                                 for branch in self._branches})
        material = deepcopy(self._fingerprint_material)
        material.update(branch_configuration=signature, web_instructions=instruction_hash)
        return signature, _sha(material), instruction_hash, deepcopy(prepared), artifacts

    def submit(self, *, user_id: UUID, resume_id: UUID, reviewed_resume: dict,
               filename: str, confirmed_at: datetime, job_family: JobFamily, force: bool = False,
               rebuild_report: bool = False) -> SkillGapRun:
        """Submit a snapshot; force always requests fresh completed-branch evidence.

        The service-only rebuild_report option bypasses a completed report, not
        evidence validation. It allows recalculation from incremental evidence
        without changing the authenticated HTTP request/response schema.
        """
        reviewed = deepcopy(reviewed_resume)
        owner, resume = str(UUID(str(user_id))), str(UUID(str(resume_id)))
        resume_hash = _sha(reviewed)
        signature, fingerprint, instruction_hash = self.branch_signature, self.fingerprint, self.instructions_sha256
        prepared, configuration_artifacts = {}, {}
        if self._latest_versions:
            signature, fingerprint, instruction_hash, prepared, configuration_artifacts = self._resolve_latest(
                reviewed, resume, job_family)
        cache_key = self._cache_key(owner, resume, resume_hash, job_family, fingerprint)
        with self._lock:
            prior_id = self._keys.get(cache_key)
            if prior_id is not None:
                prior = self._states[prior_id]
                # Force never duplicates an already queued/running paid request.
                if prior["status"] in ("queued", "running") or (not force and not rebuild_report):
                    return self._view(prior, reused=True)
            if sum(s["status"] in ("queued", "running") for s in self._states.values()) >= 8:
                raise RuntimeError("Analysis queue is full. Wait for a run to finish.")
            identifier = uuid4().hex
            state = {"id": identifier, "user_id": owner, "resume_id": resume,
                     "status": "queued", "phase": "queued",
                     "job_family": job_family, "filename": filename,
                     "resume_hash": resume_hash, "created_at": _now(), "completed_at": None,
                     "elapsed_seconds": 0.0, "model_calls": 0, "error": None,
                     "cache_key": cache_key, "confirmed_at": confirmed_at.isoformat(),
                     "calculation_fingerprint": fingerprint,
                     "prompt_revision": self.prompt_revision,
                     "instructions_sha256": instruction_hash,
                     "response_processing_version": RESPONSE_PROCESSING_VERSION,
                     "extraction_strategy": "skill_groups",
                     "branch_cache_policy": "bypass" if force else "reuse",
                     "rebuild_report": bool(rebuild_report),
                     "core_skill_cards": self.core_cards.signature(job_family)}
            state["branch_configuration"] = deepcopy(signature)
            state["version_selection"] = "latest_saved" if self._latest_versions else "pinned"
            state["reuse_from_run_id"] = (prior_id if prior_id and prior["status"] == "failed" else None)
            folder = self._folder(identifier)
            folder.mkdir()
            save_json(folder / "reviewed_resume.json", {"confirmed": True,
                "user_id": owner, "resume_id": resume, "resume_source": "resumes.confirmed_data",
                "confirmed_at": confirmed_at.isoformat(), "filename": filename,
                "resume_hash": resume_hash, "job_family": job_family, "reviewed_resume": reviewed})
            self._states[identifier] = state
            self._keys[cache_key] = identifier
            try:
                if self._latest_versions:
                    self._prepared_runs[identifier] = prepared
                    for (branch, name), value in configuration_artifacts.items():
                        save_json(folder / "branches" / branch / name, value)
                self._persist(state)
                self._executor.submit(self._work, identifier, reviewed)
            except BaseException:
                # Preserve the upstream queue-submission rollback protection.
                self._states.pop(identifier, None)
                self._prepared_runs.pop(identifier, None)
                if prior_id is None:
                    self._keys.pop(cache_key, None)
                else:
                    self._keys[cache_key] = prior_id
                raise
            return self._view(state)

    def get(self, identifier: str, *, user_id: UUID) -> SkillGapRun:
        with self._lock:
            self._folder(identifier)
            state = self._states.get(identifier)
            if state is None or state["user_id"] != str(user_id):
                raise KeyError(identifier)
            return self._view(state)

    def latest(self, *, user_id: UUID, resume_id: UUID,
               reviewed_resume: dict, job_family: JobFamily) -> SkillGapRun:
        fingerprint = self.fingerprint
        if self._latest_versions:
            _, fingerprint, _, _, _ = self._resolve_latest(deepcopy(reviewed_resume), str(resume_id), job_family)
        key = self._cache_key(str(user_id), str(resume_id), _sha(reviewed_resume), job_family, fingerprint)
        with self._lock:
            identifier = self._keys.get(key)
            if identifier is None:
                raise KeyError("No current analysis")
            return self.get(identifier, user_id=user_id)

    def _reuse_branch(self, state: dict, branch: str, payload: dict, folder: Path) -> dict | None:
        """An explicit retry may reuse checked siblings from the same failed run.

        The full resume/configuration cache key is required because global evidence
        IDs can move when any section changes. Completed runs forced by the user
        are always extracted again, not served from this retry-only cache.
        """
        previous_id = state.get("reuse_from_run_id")
        if not previous_id:
            return None
        with self._lock:
            previous = deepcopy(self._states.get(previous_id))
        if (not previous or previous["status"] != "failed"
                or previous["cache_key"] != state["cache_key"]
                or previous.get("extraction_strategy") != "skill_groups"
                or previous.get("branches", {}).get(branch, {}).get("status") != "completed"):
            return None
        source = self._folder(previous_id) / "branches" / branch
        try:
            if _canonical(load(source / "input.json")) != _canonical(payload):
                return None
            output = load(source / "agent.response.json")
            checks = self._branch_checks(output, payload)
            if checks["global_errors"] or any(row["status"] != "passed" for row in checks["skills"].values()):
                return None
            target = folder / "branches" / branch
            for name in _ARTIFACTS:
                if (source / name).is_file():
                    save_json(target / name, load(source / name))
        except (OSError, ValueError, TypeError, KeyError):
            return None
        with self._lock:
            state["branches"][branch].update(status="completed", reused=True, source_run_id=previous_id,
                original_model_calls=previous["branches"][branch].get("original_model_calls",
                    previous["branches"][branch].get("model_calls", 0)))
            self._persist(state)
        return output

    def _branch_cache_arguments(self, state: dict, branch: str, payload: dict) -> dict:
        signature = state["branch_configuration"]
        return {
            "owner": state["user_id"], "resume_id": state["resume_id"],
            "branch": branch, "payload": payload,
            "binding": {**signature["branches"][branch],
                        "project_endpoint": signature["project_endpoint"],
                        "transport_version": signature["transport_version"]},
            "dependencies": {
                "schema_name": signature["schema_name"],
                "schema_sha256": signature["schema_sha256"],
                "schema_file_sha256": signature["schema_file_sha256"],
                "core_cards": self.core_cards.signature(payload["job_family"]),
                "response_processing": RESPONSE_PROCESSING_VERSION,
                "partition_policy": self._partition_policy,
                "selection_policy": self._selection_policy,
            },
        }

    def _branch_checks(self, output: dict, payload: dict) -> dict:
        return validate_group_output(output, payload, self.catalog)

    def _reuse_incremental_branch(self, state: dict, branch: str, payload: dict,
                                  folder: Path) -> dict | None:
        if state.get("branch_cache_policy") != "reuse":
            return None
        started = time.perf_counter()
        hit = self.branch_cache.lookup(**self._branch_cache_arguments(state, branch, payload),
                                       validate=self._branch_checks)
        if hit is None:
            return None
        target = folder / "branches" / branch
        save_json(target / "agent.response.json", hit.output)
        for name in ("observed_agent.json", "configuration_check.json"):
            if name in hit.artifacts:
                save_json(target / name, hit.artifacts[name])
        if "agent.raw.json" in hit.artifacts:
            # This response belongs to its source run, not to a new paid call.
            save_json(target / "source_agent.raw.json", hit.artifacts["agent.raw.json"])
        save_json(target / "cache_provenance.json", {
            "cache_version": BRANCH_CACHE_VERSION, "cache_key": hit.key,
            "source_run_id": hit.source_run_id,
            "source_resume_id": hit.source_resume_id,
            "original_model_calls": hit.original_model_calls,
            "current_model_calls": 0, "id_remapping": hit.id_remapping,
            "revalidated_status": hit.validation["status"],
            "scope": "same_branch_input_with_checked_reference_remapping_not_semantic_verification",
        })
        with self._lock:
            state["branches"][branch].update(
                status="completed", reused=True, cache_hit=True,
                cache_key=hit.key, source_run_id=hit.source_run_id,
                source_resume_id=hit.source_resume_id,
                original_model_calls=hit.original_model_calls,
                validation_status=hit.validation["status"],
                elapsed_seconds=round(time.perf_counter() - started, 3))
            self._persist(state)
        return hit.output

    def _store_incremental_branch(self, state: dict, branch: str, payload: dict,
                                  output: dict, folder: Path) -> None:
        """Cache transport results; partial evidence remains partial on reuse.

        Cache storage is an optimization, never a reason to repair evidence or
        fail an otherwise completed model request. The merge below still runs
        the original normalizer, validation gates, and conservative selection.
        """
        source = folder / "branches" / branch
        try:
            checks = self._branch_checks(output, payload)
            artifacts = {name: load(source / name) for name in (
                "observed_agent.json", "configuration_check.json", "agent.raw.json")
                if (source / name).is_file()}
            stored = self.branch_cache.store(
                **self._branch_cache_arguments(state, branch, payload),
                output=output, validation=checks, source_run_id=state["id"],
                artifacts=artifacts, original_model_calls=state["branches"][branch]["model_calls"])
        except (OSError, ValueError, TypeError, KeyError):
            stored = False
        with self._lock:
            state["branches"][branch]["cache_stored"] = stored

    def _work_branches(self, state: dict, payload: dict, folder: Path, timings: dict) -> tuple[dict, dict]:
        if self._configuration_signature(self.settings) != self.branch_signature:
            raise SkillGapConfigurationError("local_instructions_changed",
                "The skill-group configuration changed after the API started. Restart the API, then retry. No model call was made.")
        payloads = self._make_branch_payloads(payload)
        active = [branch for branch in self._branches if any(source["units"] for source in payloads[branch]["resume_sources"])]
        outputs = {branch: absent_output(payloads[branch]) for branch in self._branches if branch not in active}
        with self._lock:
            state["branches"] = {branch: {"status": "pending" if branch in active else "skipped_empty",
                "model_calls": 0, "elapsed_seconds": 0.0, "reused": False, "error_code": None,
                "agent_name": state["branch_configuration"]["branches"][branch]["agent_name"],
                "agent_version": (state["branch_configuration"]["branches"][branch]["agent_version"]
                                  if branch in active else None)} for branch in self._branches}
            self._persist(state)

        def save_branch(branch: str, name: str, value: object) -> None:
            if branch not in self._branches or name not in _ARTIFACTS:
                raise ValueError("Unexpected branch artifact")
            save_json(folder / "branches" / branch / name, value)

        for branch in self._branches:
            save_branch(branch, "input.json", payloads[branch])
        for branch in active:
            reused = self._reuse_branch(state, branch, payloads[branch], folder)
            if reused is None:
                reused = self._reuse_incremental_branch(state, branch, payloads[branch], folder)
            if reused is not None:
                outputs[branch] = reused
        pending = [branch for branch in active if branch not in outputs]
        # Validate every required saved Agent version before making any paid call.
        if self._latest_versions:
            snapshot = self._prepared_runs.get(state["id"])
            if snapshot is None or any(branch not in snapshot for branch in pending):
                raise SkillGapConfigurationError("resolved_versions_unavailable",
                    "This analysis has no saved version snapshot. Start a new analysis explicitly.")
            prepared = {branch: snapshot[branch] for branch in pending}
        else:
            prepared = self._branch_preflight(pending, save_branch, settings=self.settings) if pending else {}
        if set(prepared) != set(pending):
            raise SkillGapConfigurationError("incomplete_branch_configuration",
                "All required evidence Agents must pass configuration checks before analysis can start.")
        if self._configuration_signature(self.settings) != self.branch_signature:
            raise SkillGapConfigurationError("local_instructions_changed",
                "The skill-group configuration changed during preflight. Restart the API, then retry. No model call was made.")
        with self._lock:
            for branch in pending:
                state["branches"][branch]["status"] = "ready"
            self._persist(state)

        def extract(branch: str) -> dict:
            started = time.perf_counter()
            branch_timings: dict = {}

            def on_request() -> None:
                with self._lock:
                    node = state["branches"][branch]
                    if node["model_calls"] != 0:
                        raise RuntimeError("Each evidence branch permits one model request only")
                    node.update(model_calls=1, status="running")
                    state.update(model_calls=state["model_calls"] + 1, phase="agent")
                    self._persist(state)

            try:
                output = self._branch_invoke(prepared[branch], payloads[branch],
                    lambda name, value: save_branch(branch, name, value), on_request, branch_timings)
                if state["branches"][branch]["model_calls"] != 1:
                    raise RuntimeError("The evidence invoker did not account for its model request")
                save_branch(branch, "agent.response.json", output)
                self._store_incremental_branch(state, branch, payloads[branch], output, folder)
                with self._lock:
                    state["branches"][branch]["status"] = "completed"
                return output
            except Exception as error:
                with self._lock:
                    state["branches"][branch].update(status="failed",
                        error_code=error.code if isinstance(error, SkillGapConfigurationError) else "branch_analysis_failed")
                raise
            finally:
                with self._lock:
                    state["branches"][branch]["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                    timings.setdefault("branches", {})[branch] = branch_timings
                    state["azure_phase_timings"] = deepcopy(timings)
                    self._persist(state)

        failures = {}
        if pending:
            # The parent queue has one worker; use a separate bounded pool here.
            # Waiting on children in the parent pool would deadlock it.
            with ThreadPoolExecutor(max_workers=len(pending), thread_name_prefix="skill-gap-evidence") as executor:
                futures = {executor.submit(extract, branch): branch for branch in pending}
                for future in as_completed(futures):
                    branch = futures[future]
                    try:
                        outputs[branch] = future.result()
                    except Exception as error:
                        failures[branch] = error
        if failures:
            branch = next(branch for branch in self._branches if branch in failures)
            error = failures[branch]
            if isinstance(error, SkillGapConfigurationError):
                raise error
            raise SkillGapConfigurationError("branch_analysis_failed",
                f"The {branch} evidence Agent could not finish. Successful branches were saved; retry explicitly to reuse them.") from None
        return self._merge_outputs(payload["job_family"], outputs, self.catalog, payload["resume_sources"])

    def _work(self, identifier: str, reviewed: dict) -> None:
        started = time.perf_counter()
        with self._lock:
            state = self._states[identifier]
        folder = self._folder(identifier)

        def save(name: str, value: object) -> None:
            if name not in _ARTIFACTS:
                raise ValueError("Unexpected artifact name")
            save_json(folder / name, value)

        timings: dict = {}
        try:
            with self._lock:
                state.update(status="running", phase="preparing")
                self._persist(state)
            payload = prepare(state["job_family"], reviewed, state["resume_id"], self.catalog,
                              core_cards=self.core_cards)
            save("input.json", payload)
            output, extraction_audit = self._work_branches(state, payload, folder, timings)
            save("extraction_audit.json", extraction_audit)
            save("agent.response.json", output)
            with self._lock:
                state.update(phase="checking", azure_phase_timings=timings)
                self._persist(state)
            report = calculate_web_report(state["job_family"], output, self.catalog, self.market, payload["resume_sources"])
            report["resume_id"] = payload["resume_id"]
            report["user_id"] = state["user_id"]
            report["database_used"] = True
            save("local_checks.json", report["reference_validation"])
            save("coverage_audit.json", report["evidence_coverage"])
            save("response_processing.json", report["response_processing"])
            save("skill_gaps.json", report)
            with self._lock:
                state.update(status="completed", phase="completed", completed_at=_now(),
                             worker_seconds=round(time.perf_counter() - started, 3))
                state['elapsed_seconds'] = round((datetime.now(timezone.utc) -
                    datetime.fromisoformat(state['created_at'])).total_seconds(), 3)
                self._persist(state)
        except Exception as error:
            # Keep detailed SDK errors out of HTTP responses and do not retry.
            # The original response/artifacts, if any, remain local for diagnosis.
            with self._lock:
                for branch in state.get("branches", {}).values():
                    if branch["status"] in {"pending", "ready"}:
                        branch.update(status="not_started", error_code="preflight_or_parent_failed")
                state.update(status="failed", phase="failed", completed_at=_now(),
                             worker_seconds=round(time.perf_counter() - started, 3),
                             error=error.public_message if isinstance(error, SkillGapConfigurationError) else
                                 "Analysis could not finish. Check the local Agent configuration and login, then retry explicitly.",
                             error_code=error.code if isinstance(error, SkillGapConfigurationError) else "analysis_failed",
                             azure_phase_timings=timings,
                             error_type=type(error).__name__)
                state['elapsed_seconds'] = round((datetime.now(timezone.utc) -
                    datetime.fromisoformat(state['created_at'])).total_seconds(), 3)
                self._persist(state)

        finally:
            with self._lock:
                self._prepared_runs.pop(identifier, None)

    def close(self) -> None:
        self._executor.shutdown(wait=True)


_manager_lock = Lock()


@lru_cache(maxsize=1)
def _cached_skill_gap_run_manager() -> SkillGapRunManager:
    return SkillGapRunManager()


def get_skill_gap_run_manager() -> SkillGapRunManager:
    # lru_cache alone allows concurrent cold misses to construct two workers.
    # Guard both the cache lookup and construction so first requests share one.
    with _manager_lock:
        return _cached_skill_gap_run_manager()
