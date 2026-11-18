"""The two authenticated read operations exposed to the single Copilot Agent."""
from copy import deepcopy
import json
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.copilot import CopilotSource, ReportReadArguments, ResumeReadArguments
from app.schemas.skill_gap_web import JobFamily
from app.services.copilot.readonly import ReadOnlyResumeSource
from app.services.copilot.reports import ReadOnlyReportSource

MAX_TOOL_CHARACTERS = 80_000


class ToolContractError(ValueError):
    pass


def tool_definitions(export_schema) -> list[dict]:
    return [
        {"type": "function", "name": "get_confirmed_resume", "strict": True,
         "description": "Read selected sections of the caller's confirmed resume for the selected career direction. Read-only; no identity, SQL or resume ID arguments.",
         "parameters": export_schema(ResumeReadArguments)},
        {"type": "function", "name": "get_skill_gap_report", "strict": True,
         "description": "Read the existing skill-gap report matching the caller, selected direction and current confirmed resume. Does not run analysis, recompute scores or generate recommendations.",
         "parameters": export_schema(ReportReadArguments)},
    ]


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate argument key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON argument")


def _excerpt(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 4000 else text[:3950] + " … (excerpt)"


def _report_excerpt(data: dict) -> str:
    report = data["report"]
    lines = [f"Saved report: {data['run_id']}", f"Completed: {data['completed_at']}",
             f"Career direction: {data['job_family']}",
             f"Policy: {report.get('policy_version', 'not recorded')}",
             str(data.get("freshness", "Saved report; current algorithm not revalidated.")),
             "Saved values: skill | evidence strength | gap | priority | calculation state"]
    for skill in report.get("skills", []):
        values = [skill.get("skill_name") or skill.get("skill_id") or "Skill",
                  *("not scored" if skill.get(key) is None else str(skill[key])
                    for key in ("resume_evidence_strength", "skill_gap", "priority")),
                  skill.get("calculation_state", "not recorded")]
        lines.append(" | ".join(str(value) for value in values))
    return "\n".join(lines)


class ReadOnlyTools:
    def __init__(self, user_id: UUID, job_family: JobFamily,
                 resumes: ReadOnlyResumeSource, reports: ReadOnlyReportSource,
                 *, report_id: str | None = None):
        self.user_id = user_id
        self.job_family = job_family
        self.resumes = resumes
        self.reports = reports
        self.report_id = report_id
        self.sources: dict[str, CopilotSource] = {}
        self._snapshot = None
        self._cache: dict[tuple[str, str], dict] = {}
        self.executions = 0
        self._characters = 0

    def _resume(self):
        if self._snapshot is None:
            self._snapshot = self.resumes.get_snapshot(self.user_id, self.job_family)
        return self._snapshot

    def _source(self, identifier: str, label: str, value) -> dict:
        source = CopilotSource(id=identifier, label=label[:200], excerpt=_excerpt(value))
        return source.model_dump()

    @staticmethod
    def validate_call(name: str, raw_arguments: str):
        try:
            if not isinstance(raw_arguments, str) or len(raw_arguments) > 8000:
                raise ValueError("Invalid argument size")
            arguments = json.loads(raw_arguments, object_pairs_hook=_object, parse_constant=_constant)
            model = {"get_confirmed_resume": ResumeReadArguments,
                     "get_skill_gap_report": ReportReadArguments}.get(name)
            if model is None:
                raise ValueError("Unregistered tool")
            parsed = model.model_validate(arguments)
        except (TypeError, ValueError, ValidationError):
            raise ToolContractError("Copilot requested an invalid read operation.") from None
        return parsed

    def execute(self, name: str, raw_arguments: str) -> dict:
        parsed = self.validate_call(name, raw_arguments)
        key = (name, json.dumps(parsed.model_dump(), sort_keys=True))
        if key in self._cache:
            return deepcopy(self._cache[key])
        if self.executions >= 2:
            return {"status": "read_limit", "message": "The read limit for this turn has been reached. Answer using only results already obtained."}
        self.executions += 1
        try:
            if name == "get_confirmed_resume":
                snapshot = self._resume()
                sections = {section: deepcopy(snapshot.confirmed_data[section]) for section in parsed.sections}
                data = {"resume_id": str(snapshot.id), "filename": snapshot.filename,
                        "job_family": snapshot.job_family, "confirmed_at": snapshot.confirmed_at,
                        "sections": sections}
                sources = [self._source(f"resume:{snapshot.id}:{section}",
                    "Saved résumé · " + section.replace("_", " "),
                    {"confirmed_at": snapshot.confirmed_at, "content": value})
                    for section, value in sections.items()]
            else:
                data = self.reports.get_report(self._resume(), report_id=self.report_id)
                # One report is one document, even if it describes many skills. Together with
                # the five possible resume sections, the entire turn offers at most six IDs.
                # The complete saved report still reaches the model unchanged in data.
                sources = [self._source(f"report:{data['run_id']}:summary", "Saved skill-gap report",
                                       _report_excerpt(data))]
            # The data is already present once; only send ID mappings to the model.
            # The backend keeps the excerpts for the final user-visible citations.
            result = {"status": "ok", "data": data,
                      "sources": [{"id": source["id"], "label": source["label"]} for source in sources]}
            encoded = json.dumps(result, ensure_ascii=False, default=str)
            if len(encoded) > MAX_TOOL_CHARACTERS or self._characters + len(encoded) > 100_000:
                raise HTTPException(503, "The saved data is too large for this turn. Ask about fewer resume sections.")
            self._characters += len(encoded)
            for source in sources:
                self.sources[source["id"]] = CopilotSource.model_validate(source)
        except HTTPException as error:
            result = {"status": "unavailable", "status_code": error.status_code,
                      "message": error.detail if isinstance(error.detail, str) else "The saved data is unavailable."}
        self._cache[key] = deepcopy(result)
        return result

    def selected_sources(self, identifiers: list[str]) -> list[CopilotSource]:
        if (self.sources and not identifiers or len(set(identifiers)) != len(identifiers)
                or any(identifier not in self.sources for identifier in identifiers)):
            raise ToolContractError("Copilot returned an unverified source reference.")
        return [self.sources[identifier] for identifier in identifiers]
