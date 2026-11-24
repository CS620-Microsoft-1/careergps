"""Where SkillGapRunManager keeps run state and finished reports.

Both stores take the same calls: `create` (a new queued run), `save_state` (progress), `complete`
(the finished run with its report), `load_states` (start-up recovery) and `load_report`.

- `JsonRunStore` is the original behaviour: one folder per run under the manager's directory, with
  status.json (the manager's state), run.json (a readable manifest) and skill_gaps.json (the report,
  written by the worker).
- `DbRunStore` keeps the same state in skill_gap_runs, skill_gap_run_branches and skill_gap_results
  (contract v3). Each call is one short transaction; none is open while an Agent runs.

Branch inputs, raw responses and the branch cache stay in the local run folders for every store.
"""
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.skill_gap import SkillGapResult, SkillGapRunBranch, SkillGapRunRecord
from .persistence import branch_row, completion_fields, queued_run_row, result_rows, run_uuid
from .schema import SCHEMA_NAME
from .scoring import POLICY_VERSION
from .storage import load, save_json

RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


def run_folder(directory: Path, identifier: str) -> Path:
    """The run's artifact folder. Run ids are uuid4().hex; anything else is not a run."""
    if not RUN_ID.fullmatch(identifier):
        raise KeyError(identifier)
    return directory / identifier


class ActiveRunExists(RuntimeError):
    """The same résumé, role and configuration already has a queued or running analysis."""


class JsonRunStore:
    """Run state as local JSON files (the original storage)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def create(self, state: dict, reviewed_resume: dict, **_run_fields: Any) -> None:
        # The worker keeps the snapshot in reviewed_resume.json; the state is all this store needs.
        self.save_state(state)

    def complete(self, state: dict, **_result: Any) -> None:
        # The worker already wrote skill_gaps.json and the audit files.
        self.save_state(state)

    def save_state(self, state: dict) -> None:
        folder = run_folder(self.directory, state["id"])
        save_json(folder / "status.json", state)
        save_json(folder / "run.json", {
            "mode": "authenticated_web", "status": state["status"], "phase": state["phase"],
            "user_id": state["user_id"], "resume_id": state["resume_id"],
            "resume_source": "resumes.confirmed_data", "result_storage": "local_json",
            "job_family": state["job_family"], "resume_hash": state["resume_hash"],
            "policy_version": state.get("policy_version", POLICY_VERSION),
            "expected_schema_name": state.get("response_schema_name", SCHEMA_NAME),
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

    def load_states(self) -> Iterator[dict]:
        """Every saved state whose folder name matches its id, in folder order; unreadable ones are skipped.

        The caller still validates each state before trusting it.
        """
        for path in sorted(self.directory.glob("*/status.json")):
            if not RUN_ID.fullmatch(path.parent.name):
                continue
            try:
                state = load(path)
                if state["id"] != path.parent.name:
                    continue
            except (OSError, ValueError, TypeError, KeyError):
                continue
            yield state

    def load_report(self, identifier: str) -> dict:
        return load(run_folder(self.directory, identifier) / "skill_gaps.json")


def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


_BRANCH_PROGRESS = ("status", "agent_name", "agent_version", "model_calls", "elapsed_seconds", "reused",
                    "error_code", "source_run_id")


class DbRunStore:
    """Run state in PostgreSQL (skill_gap_runs, skill_gap_run_branches, skill_gap_results)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    # -- writes -----------------------------------------------------------------------------------

    def create(self, state: dict, reviewed_resume: dict, *, demand_snapshot_fingerprint: str,
               catalog_version: str | None, partition_policy_version: str, selection_policy_version: str) -> None:
        """Insert the queued run. The database allows one queued/running run per résumé, role and configuration."""
        row = queued_run_row(state, reviewed_resume, demand_snapshot_fingerprint=demand_snapshot_fingerprint,
                             catalog_version=catalog_version, partition_policy_version=partition_policy_version,
                             selection_policy_version=selection_policy_version)
        try:
            with self.session_factory() as session, session.begin():
                row["reuse_from_run_id"] = self._existing(session, row["reuse_from_run_id"])
                session.add(SkillGapRunRecord(**row))
        except IntegrityError as error:
            if "uq_skill_gap_runs_one_active" in str(error.orig):
                raise ActiveRunExists("This résumé already has an analysis in progress.") from None
            raise

    def save_state(self, state: dict) -> None:
        """Progress: status, phase, counts, error and each branch's progress.

        A completed run is written only by `complete`, together with its report.
        """
        if state["status"] == "completed":
            return
        run_id = run_uuid(state["id"])
        with self.session_factory() as session, session.begin():
            session.execute(update(SkillGapRunRecord).where(SkillGapRunRecord.id == run_id).values(
                status=state["status"], phase=state["phase"], model_calls=state["model_calls"],
                elapsed_seconds=state["elapsed_seconds"], completed_at=_timestamp(state.get("completed_at")),
                error=state.get("error"), error_code=state.get("error_code"),
                timings=state.get("azure_phase_timings") or {}))
            for branch, progress in state.get("branches", {}).items():
                values = {key: progress.get(key) for key in _BRANCH_PROGRESS}
                values.update(model_calls=values["model_calls"] or 0, elapsed_seconds=values["elapsed_seconds"] or 0.0,
                              reused=bool(values["reused"]),
                              source_run_id=self._existing(session, run_uuid(values["source_run_id"])))
                self._upsert_branch(session, {"run_id": run_id, "branch": branch, **values})

    def complete(self, state: dict, *, report: dict, extraction_audit: dict | None, merged_output: Any,
                 branches: dict[str, dict]) -> None:
        """One transaction: the completed run, every branch with its raw answer, and one row per skill.

        `branches` maps each group to branch_row's keyword arguments (payload, output, raw_response,
        definition, timings, validation, response_processing).
        """
        run_id, user_id = run_uuid(state["id"]), UUID(state["user_id"])
        results = result_rows(report, extraction_audit, run_id=run_id, user_id=user_id, job_family=state["job_family"])
        with self.session_factory() as session, session.begin():
            session.execute(update(SkillGapRunRecord).where(SkillGapRunRecord.id == run_id).values(
                status="completed", phase="completed", completed_at=_timestamp(state["completed_at"]),
                elapsed_seconds=state["elapsed_seconds"], model_calls=state["model_calls"],
                error=None, error_code=None, timings=state.get("azure_phase_timings") or {},
                **completion_fields(report, extraction_audit, merged_output)))
            for branch, progress in state.get("branches", {}).items():
                row = branch_row(run_id, branch, progress, **branches.get(branch, {}))
                row["source_run_id"] = self._existing(session, row["source_run_id"])
                self._upsert_branch(session, row)
            session.execute(delete(SkillGapResult).where(SkillGapResult.run_id == run_id))
            session.add_all(SkillGapResult(**row) for row in results)

    # -- reads ------------------------------------------------------------------------------------

    def load_states(self) -> Iterator[dict]:
        """Every run as the manager's state (without report or snapshot), oldest first.

        Like the JSON store, the caller validates each state and fails runs still queued or running.
        """
        with self.session_factory() as session:
            runs = session.scalars(select(SkillGapRunRecord).order_by(SkillGapRunRecord.created_at,
                                                                      SkillGapRunRecord.id)).all()
            branches: dict[UUID, dict] = {}
            for row in session.scalars(select(SkillGapRunBranch)):
                branches.setdefault(row.run_id, {})[row.branch] = {
                    "status": row.status, "agent_name": row.agent_name, "agent_version": row.agent_version,
                    "model_calls": row.model_calls, "elapsed_seconds": row.elapsed_seconds, "reused": row.reused,
                    "error_code": row.error_code,
                    **({"source_run_id": row.source_run_id.hex} if row.source_run_id else {})}
            states = [self._state(run, branches.get(run.id, {})) for run in runs]
        yield from states

    def load_report(self, identifier: str) -> dict:
        with self.session_factory() as session:
            report = session.scalar(select(SkillGapRunRecord.report).where(SkillGapRunRecord.id == run_uuid(identifier)))
        if report is None:
            raise KeyError(identifier)
        return report

    # -- helpers ----------------------------------------------------------------------------------

    @staticmethod
    def _existing(session: Session, run_id: UUID | None) -> UUID | None:
        """A link to another run, or None when that run exists only in old local files."""
        if run_id is None:
            return None
        return session.scalar(select(SkillGapRunRecord.id).where(SkillGapRunRecord.id == run_id))

    @staticmethod
    def _upsert_branch(session: Session, values: dict) -> None:
        changes = {key: value for key, value in values.items() if key not in ("run_id", "branch")}
        statement = insert(SkillGapRunBranch).values(**values)
        session.execute(statement.on_conflict_do_update(
            index_elements=["run_id", "branch"],
            set_={**changes, "updated_at": datetime.now(timezone.utc)}))

    @staticmethod
    def _state(run: SkillGapRunRecord, branches: dict) -> dict:
        state = {
            "id": run.id.hex, "user_id": str(run.user_id), "resume_id": str(run.resume_id),
            "status": run.status, "phase": run.phase, "job_family": run.job_family,
            "filename": run.resume_filename, "resume_hash": run.resume_hash,
            "created_at": _iso(run.created_at), "completed_at": _iso(run.completed_at),
            "elapsed_seconds": run.elapsed_seconds, "model_calls": run.model_calls, "error": run.error,
            "error_code": run.error_code, "confirmed_at": _iso(run.confirmed_at),
            "calculation_fingerprint": run.calculation_fingerprint, "prompt_revision": run.prompt_revision,
            "instructions_sha256": run.instructions_sha256,
            "response_processing_version": run.response_processing_version,
            "extraction_strategy": run.extraction_strategy,
            "reuse_from_run_id": run.reuse_from_run_id.hex if run.reuse_from_run_id else None,
            "azure_phase_timings": run.timings or {},
        }
        if branches:
            state["branches"] = branches
        return state
