"""Where SkillGapRunManager keeps run state and finished reports.

`JsonRunStore` is the original behaviour: one folder per run under the manager's directory, with
status.json (the manager's state), run.json (a readable manifest) and skill_gaps.json (the report,
written by the worker). Branch inputs, raw responses and the branch cache stay in those folders for
every store.
"""
from collections.abc import Iterator
from pathlib import Path
import re

from .schema import SCHEMA_NAME
from .scoring import POLICY_VERSION
from .storage import load, save_json

RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


def run_folder(directory: Path, identifier: str) -> Path:
    """The run's artifact folder. Run ids are uuid4().hex; anything else is not a run."""
    if not RUN_ID.fullmatch(identifier):
        raise KeyError(identifier)
    return directory / identifier


class JsonRunStore:
    """Run state as local JSON files (the original storage)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save_state(self, state: dict) -> None:
        folder = run_folder(self.directory, state["id"])
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
