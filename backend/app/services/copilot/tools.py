"""Only these two read-only functions may be dispatched by the Copilot Agent.

Fixtures are intentionally identical for all signed-in users. No real resume, analysis,
resource catalog or database is read. The authenticated context is server-supplied.
"""
from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError

from app.schemas.copilot import CopilotSource, GapArguments, SuggestionArguments, ToolResult


@dataclass(frozen=True)
class ToolContext:
    user_id: UUID


FIXTURES = {
    "sql": {
        "name": "SQL and databases", "priority": 1,
        "evidence": "Built a task tracker using React and TypeScript. No SQL queries or relational schema design are described.",
        "requirement": "Use SQL queries and joins to retrieve data from relational databases.",
        "finding": "The sample resume has no explicit evidence for the SQL requirement. This does not prove the person lacks SQL skills.",
        "learning": "Practice SELECT, filtering, JOIN and GROUP BY on a small relational database.",
        "project": "Add related task and user tables to the task tracker, implement joins, and document the queries.",
        "hours": 6,
    },
    "deployment": {
        "name": "Application deployment", "priority": 2,
        "evidence": "Built a working local task tracker. Hosting, releases and monitoring are not described.",
        "requirement": "Deploy an application and use logs to investigate operational problems.",
        "finding": "The sample resume has limited evidence of deployment and operations; actual experience is unknown.",
        "learning": "Learn environment configuration, release steps, application logs and rollback basics.",
        "project": "Deploy the task tracker, inspect logs and write a repeatable release and rollback guide.",
        "hours": 5,
    },
    "testing": {
        "name": "Software testing", "priority": 3,
        "evidence": "Implemented reusable task-tracker components. Automated tests and edge cases are not described.",
        "requirement": "Write automated tests for normal behavior, invalid input and regressions.",
        "finding": "The sample resume has limited evidence of automated testing; this is not proof of a missing skill.",
        "learning": "Practice test cases, assertions, edge cases and regression testing.",
        "project": "Test task creation, editing and completion, including invalid inputs, and document one prevented regression.",
        "hours": 4,
    },
}

TOOLS = [
    {"type": "function", "name": "get_skill_gap_analysis", "strict": True,
     "description": "Read the fictional SWE skill-gap report and its evidence. Use null for the full report. Does not start or modify an analysis.",
     "parameters": GapArguments.model_json_schema()},
    {"type": "function", "name": "get_learning_suggestions", "strict": True,
     "description": "Get fictional learning/project suggestions for a skill. First read get_skill_gap_analysis. Use null for hours unless the user supplied a budget.",
     "parameters": SuggestionArguments.model_json_schema()},
]


def _sources(skill_id: str) -> list[CopilotSource]:
    item = FIXTURES[skill_id]
    return [CopilotSource(id=f"sample-{kind}-{skill_id}", label=label, excerpt=item[field])
            for kind, label, field in [
                ("resume", "Sample resume · Projects", "evidence"),
                ("role", f"Sample SWE role · {item['name']}", "requirement"),
                ("report", f"Sample report v1 · {item['name']}", "finding"),
            ]]


class MockCopilotTools:
    def __init__(self, context: ToolContext):
        self.context = context
        self.read_skills: set[str] = set()

    def dispatch(self, name: str, arguments: str) -> ToolResult:
        if name not in {"get_skill_gap_analysis", "get_learning_suggestions"}:
            return ToolResult(status="unsupported_tool", data=None, error="This tool is not available. Only read-only sample queries are supported.")
        try:
            if len(arguments) > 2000:
                raise ValueError("Oversized arguments")
            if name == "get_skill_gap_analysis":
                return self.get_skill_gap_analysis(GapArguments.model_validate_json(arguments))
            return self.get_learning_suggestions(SuggestionArguments.model_validate_json(arguments))
        except (ValueError, ValidationError):
            return ToolResult(status="invalid_arguments", data=None,
                              error="Use a supported skill (sql, deployment, testing) and the declared arguments only.")

    def get_skill_gap_analysis(self, args: GapArguments) -> ToolResult:
        ids = [args.skill_id] if args.skill_id else list(FIXTURES)
        self.read_skills.update(ids)
        return ToolResult(status="ok", data={"target_role": "Software engineer", "report_version": "v1",
            "skills": [{"skill_id": key, "skill_name": FIXTURES[key]["name"],
                        "sample_priority": FIXTURES[key]["priority"], "finding": FIXTURES[key]["finding"]} for key in ids]},
            sources=[source for key in ids for source in _sources(key)])

    def get_learning_suggestions(self, args: SuggestionArguments) -> ToolResult:
        if args.skill_id not in self.read_skills:
            return ToolResult(status="invalid_arguments", data=None,
                error="Read get_skill_gap_analysis for this skill before requesting suggestions.")
        item = FIXTURES[args.skill_id]
        if args.available_hours is not None and args.available_hours < item["hours"]:
            return ToolResult(status="not_found", data=None,
                error="No complete sample project fits that time budget. Offer to discuss a smaller milestone; do not claim a matching project exists.")
        source = CopilotSource(id=f"sample-suggestion-{args.skill_id}", label=f"Sample suggestions · {item['name']}",
                              excerpt=f"{item['learning']} Project: {item['project']} Illustrative effort: {item['hours']} hours.")
        return ToolResult(status="ok", data={"skill_id": args.skill_id, "learning": item["learning"],
            "project": item["project"], "estimated_hours": item["hours"], "estimate_is_illustrative": True}, sources=[source])
