from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    addressed_gaps: list[str] = Field(min_length=1)
    why_recommended: str = Field(min_length=1)
    prerequisites_to_check: list[str]


class ResourceRecommendations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[ProjectRecommendation] = Field(max_length=3)
    no_match_reason: str | None

    @model_validator(mode="after")
    def check_reason(self):
        if self.recommendations and self.no_match_reason is not None:
            raise ValueError("Recommendations must have a null no_match_reason.")
        if not self.recommendations and (
            not self.no_match_reason or not self.no_match_reason.strip()
        ):
            raise ValueError("Empty recommendations require a reason.")
        return self