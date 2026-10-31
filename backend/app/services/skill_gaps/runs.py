"""Owner-scoped, single-worker analysis using detached database resume snapshots.

Results remain local JSON. Workers never retain a request's ORM session, and
polling/restoring never starts a model call.
"""
from concurrent.futures import ThreadPoolExecutor
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

from app.core.config import BACKEND_ROOT
from app.schemas.skill_gap_web import JobFamily, SkillGapRun
from .response import RESPONSE_PROCESSING_VERSION, calculate_web_report
from .transport import (
    ACTIVE_INSTRUCTIONS_PATH, ACTIVE_PROMPT_REVISION, SkillGapConfigurationError, invoke,
)
from .scoring import POLICY_VERSION
from .assets import ASSET_ROOT
from .input import prepare
from .match import summarize_match
from .storage import load, save_json
from .schema import SCHEMA_NAME

_ID = re.compile(r"[0-9a-f]{32}\Z")
_ARTIFACTS = {"input.json", "reviewed_resume.json", "observed_agent.json", "agent.raw.json",
              "agent.response.json", "local_checks.json", "coverage_audit.json", "skill_gaps.json",
              "response_processing.json", "configuration_check.json"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class SkillGapRunManager:
    def __init__(self, directory: Path | None = None, *, invoker: Callable | None = None) -> None:
        self.directory = (directory or BACKEND_ROOT / "local_results" / "web_skill_gaps").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._invoke = invoker or invoke
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-skill-gap")
        self._states: dict[str, dict] = {}
        self._keys: dict[str, str] = {}
        self.catalog = load(ASSET_ROOT / "core_catalog.json")
        self.market = load(ASSET_ROOT / "market_snapshot.json")
        self.instructions_sha256 = hashlib.sha256(ACTIVE_INSTRUCTIONS_PATH.read_bytes()).hexdigest()
        self.fingerprint = _sha({"response_processing": RESPONSE_PROCESSING_VERSION,
                                "web_instructions": self.instructions_sha256,
                                "v12_assets": {name: hashlib.sha256((ASSET_ROOT / name).read_bytes()).hexdigest()
                                 for name in ("core_catalog.json", "market_snapshot.json", "scoring_policy.json",
                                              "response-format.json")}})
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

    def submit(self, *, user_id: UUID, resume_id: UUID, reviewed_resume: dict,
               filename: str, confirmed_at: datetime, job_family: JobFamily, force: bool = False) -> SkillGapRun:
        reviewed = deepcopy(reviewed_resume)
        owner, resume = str(UUID(str(user_id))), str(UUID(str(resume_id)))
        resume_hash = _sha(reviewed)
        cache_key = self._cache_key(owner, resume, resume_hash, job_family)
        with self._lock:
            prior_id = self._keys.get(cache_key)
            if prior_id is not None:
                prior = self._states[prior_id]
                # Force never duplicates an already queued/running paid request.
                if prior["status"] in ("queued", "running") or not force:
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
                     "calculation_fingerprint": self.fingerprint,
                     "prompt_revision": ACTIVE_PROMPT_REVISION,
                     "instructions_sha256": self.instructions_sha256,
                     "response_processing_version": RESPONSE_PROCESSING_VERSION}
            folder = self._folder(identifier)
            folder.mkdir()
            save_json(folder / "reviewed_resume.json", {"confirmed": True,
                "user_id": owner, "resume_id": resume, "resume_source": "resumes.confirmed_data",
                "confirmed_at": confirmed_at.isoformat(), "filename": filename,
                "resume_hash": resume_hash, "job_family": job_family, "reviewed_resume": reviewed})
            self._states[identifier] = state
            self._keys[cache_key] = identifier
            try:
                self._persist(state)
                self._executor.submit(self._work, identifier, reviewed)
            except BaseException:
                # Without a worker the run would stay queued and be reused forever.
                del self._states[identifier]
                if prior_id is None:
                    del self._keys[cache_key]
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
        key = self._cache_key(str(user_id), str(resume_id), _sha(reviewed_resume), job_family)
        with self._lock:
            identifier = self._keys.get(key)
            if identifier is None:
                raise KeyError("No current analysis")
            return self.get(identifier, user_id=user_id)

    def _work(self, identifier: str, reviewed: dict) -> None:
        started = time.perf_counter()
        with self._lock:
            state = self._states[identifier]
        folder = self._folder(identifier)

        def save(name: str, value: object) -> None:
            if name not in _ARTIFACTS:
                raise ValueError("Unexpected artifact name")
            save_json(folder / name, value)

        def on_request() -> None:
            with self._lock:
                if state["model_calls"] != 0:
                    raise RuntimeError("A run permits one model request only")
                state.update(model_calls=1, phase="agent")
                self._persist(state)

        timings: dict = {}
        try:
            with self._lock:
                state.update(status="running", phase="preparing")
                self._persist(state)
            payload = prepare(state["job_family"], reviewed, state["resume_id"], self.catalog)
            save("input.json", payload)
            if hashlib.sha256(ACTIVE_INSTRUCTIONS_PATH.read_bytes()).hexdigest() != self.instructions_sha256:
                raise SkillGapConfigurationError("local_instructions_changed",
                    "The Instructions changed after the API started. Restart the API, then retry. No model call was made.")
            output = self._invoke(payload, save, on_request, timings)
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
