"""Bounded public chat input and structured, evidence-linked Agent output."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SAMPLE_ANALYSIS_ID = "sample-swe-v1"
MAX_CONTEXT_CHARACTERS = 24_000
SkillId = Literal["sql", "deployment", "testing"]
Intent = Literal["explain_gap", "learning_advice", "clarify", "general", "unsupported_action", "tool_error"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatTurn(Contract):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=8000)


class CopilotRequest(Contract):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bounded_context(self):
        if len(self.question) + sum(len(turn.text) for turn in self.history) > MAX_CONTEXT_CHARACTERS:
            raise ValueError("Conversation context exceeds 24,000 characters.")
        return self


class CopilotSource(Contract):
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=4000)


class AgentAnswer(Contract):
    intent: Intent
    text: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(max_length=10)


class CopilotReply(Contract):
    text: str
    sources: list[CopilotSource]
    intent: Intent
    mode: Literal["foundry_mock"] = "foundry_mock"
    analysisId: Literal["sample-swe-v1"] = SAMPLE_ANALYSIS_ID


class GapArguments(Contract):
    skill_id: SkillId | None


class SuggestionArguments(Contract):
    skill_id: SkillId
    available_hours: int | None = Field(ge=1, le=40, strict=True)


class ToolResult(Contract):
    status: Literal["ok", "not_found", "invalid_arguments", "unsupported_tool", "unavailable"]
    data: dict | None
    sources: list[CopilotSource] = Field(default_factory=list)
    error: str | None = None
    analysis_id: Literal["sample-swe-v1"] = SAMPLE_ANALYSIS_ID
    data_mode: Literal["mock"] = "mock"
