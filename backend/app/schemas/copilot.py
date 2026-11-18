"""Bounded v9 conversation inputs, tool arguments and chat replies."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.skill_gap_web import JobFamily

MAX_CONTEXT_CHARACTERS = 24_000
ResumeSection = Literal["technical_skills", "education", "work_experience", "research_experience", "projects"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatTurn(Contract):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=8000)


class CopilotSource(Contract):
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=4000)


class CopilotRequest(Contract):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    jobFamily: JobFamily
    # Untrusted UI selector only; the reader rechecks owner, direction and current resume/hash.
    reportId: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None

    @model_validator(mode="after")
    def bounded_context(self):
        if len(self.question) + sum(len(turn.text) for turn in self.history) > MAX_CONTEXT_CHARACTERS:
            raise ValueError("Conversation context exceeds 24,000 characters.")
        return self


class ReadOnlyAgentAnswer(Contract):
    text: str = Field(min_length=1, max_length=8000)
    source_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(max_length=8)


class ResumeReadArguments(Contract):
    sections: list[ResumeSection] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_sections(self):
        if len(set(self.sections)) != len(self.sections):
            raise ValueError("Choose each resume section only once.")
        return self


class ReportReadArguments(Contract):
    pass


class CopilotCapabilities(Contract):
    dataReadsEnabled: bool


class CopilotReply(Contract):
    text: str = Field(min_length=1, max_length=8000)
    sources: list[CopilotSource] = Field(default_factory=list, max_length=8)
    mode: Literal["foundry_chat"] = "foundry_chat"
    jobFamily: JobFamily
