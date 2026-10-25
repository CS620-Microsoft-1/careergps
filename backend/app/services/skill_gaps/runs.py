"""Local-only, single-worker manager for the Skill Gap evidence pipeline.

No database imports or connections. A run owns its reviewed snapshot, original
Agent response and unchanged scoring report. Polling never calls the Agent.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from threading import RLock
import time
from typing import Callable
from uuid import uuid4

from app.core.config import BACKEND_ROOT
from app.schemas.skill_gap_web import SkillGapRun, SkillGapRunRequest
from .response import RESPONSE_PROCESSING_VERSION, calculate_web_report
from .transport import (
    ACTIVE_INSTRUCTIONS_PATH, ACTIVE_PROMPT_REVISION, SkillGapConfigurationError, invoke,
)
from .scoring import POLICY_VERSION, calculate as calculate_baseline
from .assets import ASSET_ROOT
from .input import prepare
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
            "mode": "local_web", "status": state["status"], "phase": state["phase"],
            "job_family": state["job_family"], "resume_hash": state["resume_hash"],
            "policy_version": POLICY_VERSION, "expected_schema_name": SCHEMA_NAME,
            "calculation_fingerprint": self.fingerprint, "database_used": False,
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
                created = datetime.fromisoformat(state["created_at"])
                if created.tzinfo is None:
                    continue
                self._view(state)  # Validate fields before trusting a local record.
                if state["status"] in ("queued", "running"):
                    state.update(status="failed", phase="failed", completed_at=_now(),
                                 error="The previous local process stopped. Start a new analysis explicitly.")
                    self._persist(state)
                self._states[state["id"]] = state
                prior = self._states.get(self._keys.get(state["cache_key"], ""))
                if prior is None or (created, state["id"]) > (
                        datetime.fromisoformat(prior["created_at"]), prior["id"]):
                    self._keys[state["cache_key"]] = state["id"]
            except (OSError, ValueError, TypeError, KeyError):
                continue

    def _view(self, state: dict, *, reused: bool = False) -> SkillGapRun:
        keys = ("id", "status", "phase", "job_family", "filename", "resume_hash", "created_at",
                "completed_at", "elapsed_seconds", "model_calls", "error")
        value = {key: deepcopy(state[key]) for key in keys}
        if state["status"] in ("queued", "running"):
            value["elapsed_seconds"] = round(max(0, (datetime.now(timezone.utc) -
                                                    datetime.fromisoformat(state["created_at"])).total_seconds()), 3)
        value["report"] = load(self._folder(state["id"]) / "skill_gaps.json") if state["status"] == "completed" else None
        value["reused"] = reused
        return SkillGapRun.model_validate(value)

    def submit(self, request: SkillGapRunRequest) -> SkillGapRun:
        reviewed = request.reviewed_resume.model_dump()
        resume_hash = _sha(reviewed)
        cache_key = _sha({"resume_hash": resume_hash, "job_family": request.job_family,
                          "contract": SCHEMA_NAME, "fingerprint": self.fingerprint})
        with self._lock:
            prior_id = self._keys.get(cache_key)
            if prior_id is not None:
                prior = self._states[prior_id]
                # Even force cannot enqueue a duplicate while this snapshot runs.
                if prior["status"] in ("queued", "running") or not request.force:
                    return self._view(prior, reused=True)
            if sum(s["status"] in ("queued", "running") for s in self._states.values()) >= 8:
                raise RuntimeError("Local analysis queue is full. Wait for a run to finish.")
            identifier = uuid4().hex
            state = {"id": identifier, "status": "queued", "phase": "queued",
                     "job_family": request.job_family, "filename": request.filename,
                     "resume_hash": resume_hash, "created_at": _now(), "completed_at": None,
                     "elapsed_seconds": 0.0, "model_calls": 0, "error": None,
                     "cache_key": cache_key, "confirmed_at": request.confirmed_at.isoformat(),
                     "prompt_revision": ACTIVE_PROMPT_REVISION,
                     "instructions_sha256": self.instructions_sha256,
                     "response_processing_version": RESPONSE_PROCESSING_VERSION}
            folder = self._folder(identifier)
            folder.mkdir()
            save_json(folder / "reviewed_resume.json", {"confirmed": True,
                "confirmed_at": request.confirmed_at.isoformat(), "filename": request.filename,
                "resume_hash": resume_hash, "job_family": request.job_family, "reviewed_resume": reviewed})
            self._states[identifier] = state
            self._keys[cache_key] = identifier
            self._persist(state)
            self._executor.submit(self._work, identifier, reviewed)
            return self._view(state)

    def get(self, identifier: str) -> SkillGapRun:
        with self._lock:
            self._folder(identifier)
            if identifier not in self._states:
                raise KeyError(identifier)
            return self._view(self._states[identifier])

    def reprocess_completed(self, identifier: str) -> SkillGapRun:
        """Explicit offline replay of one saved response; never calls the Agent.

        Historical scores/checks are archived before replacement. Refuse to
        replay if the saved input, evidence or current v12 assets do not reproduce
        the existing report, rather than applying different demand/scoring data.
        """
        with self._lock:
            folder = self._folder(identifier)
            state = self._states[identifier]
            if state["status"] != "completed":
                raise ValueError("Only completed runs can be reprocessed offline")
            old = load(folder / "skill_gaps.json")
            if old.get("response_processing", {}).get("version") == RESPONSE_PROCESSING_VERSION:
                return self._view(state, reused=True)
            started = time.perf_counter()
            payload, output = load(folder / "input.json"), load(folder / "agent.response.json")
            reviewed = load(folder / "reviewed_resume.json")
            if (_sha(reviewed["reviewed_resume"]) != state["resume_hash"]
                    or payload != prepare(state["job_family"], reviewed["reviewed_resume"],
                                          "reviewed_" + state["resume_hash"], self.catalog)):
                raise ValueError("Saved input does not match the confirmed resume snapshot")
            baseline = calculate_baseline(state["job_family"], output, self.catalog, self.market, payload["resume_sources"])
            for key in ("policy_version", "skills", "source_index", "priority_order",
                        "unscored_skill_ids", "demand_snapshot_fingerprint"):
                if baseline.get(key) != old.get(key):
                    raise ValueError("Saved report cannot be reproduced with the current v12 assets: " + key)
            report = calculate_web_report(state["job_family"], output, self.catalog, self.market,
                                          payload["resume_sources"])
            report["resume_id"] = payload["resume_id"]
            revision = folder / "report_revisions" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ"))
            revision.mkdir(parents=True)
            for name in ("skill_gaps.json", "local_checks.json", "coverage_audit.json",
                         "response_processing.json", "status.json", "run.json"):
                original = folder / name
                if original.exists():
                    (revision / name).write_bytes(original.read_bytes())
            save_json(folder / "local_checks.json", report["reference_validation"])
            save_json(folder / "coverage_audit.json", report["evidence_coverage"])
            save_json(folder / "response_processing.json", report["response_processing"])
            save_json(folder / "skill_gaps.json", report)
            old_key = state["cache_key"]
            state["cache_key"] = _sha({"resume_hash": state["resume_hash"], "job_family": state["job_family"],
                                       "contract": SCHEMA_NAME, "fingerprint": self.fingerprint})
            if self._keys.get(old_key) == identifier:
                self._keys.pop(old_key)
            prior_id = self._keys.get(state["cache_key"])
            prior = self._states.get(prior_id) if prior_id else None
            if prior is None or (state["created_at"], identifier) >= (prior["created_at"], prior["id"]):
                self._keys[state["cache_key"]] = identifier
            state.update(response_processing_version=RESPONSE_PROCESSING_VERSION,
                         local_reprocessing={"at": _now(), "additional_model_calls": 0,
                                             "seconds": round(time.perf_counter() - started, 6),
                                             "previous_report": str(revision.relative_to(folder))})
            self._persist(state)
            return self._view(state, reused=True)

    def _work(self, identifier: str, reviewed: dict) -> None:
        started = time.perf_counter()
        with self._lock:
            state = self._states[identifier]
            state.update(status="running", phase="preparing")
            self._persist(state)
        folder = self._folder(identifier)

        def save(name: str, value: object) -> None:
            if name not in _ARTIFACTS:
                raise ValueError("Unexpected artifact name")
            save_json(folder / name, value)

        def on_request() -> None:
            with self._lock:
                if state["model_calls"] != 0:
                    raise RuntimeError("A local run permits one model request only")
                state.update(model_calls=1, phase="agent")
                self._persist(state)

        timings: dict = {}
        try:
            payload = prepare(state["job_family"], reviewed, "reviewed_" + state["resume_hash"], self.catalog)
            save("input.json", payload)
            if hashlib.sha256(ACTIVE_INSTRUCTIONS_PATH.read_bytes()).hexdigest() != self.instructions_sha256:
                raise SkillGapConfigurationError("local_instructions_changed",
                    "The local Instructions changed after the API started. Restart the local API, then retry. No model call was made.")
            output = self._invoke(payload, save, on_request, timings)
            save("agent.response.json", output)
            with self._lock:
                state.update(phase="checking", azure_phase_timings=timings)
                self._persist(state)
            report = calculate_web_report(state["job_family"], output, self.catalog, self.market, payload["resume_sources"])
            report["resume_id"] = payload["resume_id"]
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


@lru_cache
def get_skill_gap_run_manager() -> SkillGapRunManager:
    return SkillGapRunManager()
