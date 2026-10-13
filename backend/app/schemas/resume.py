from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonalInformation(StrictModel):
    name: str | None
    emails: list[str]
    phones: list[str]
    location: str | None
    linkedin: str | None
    github: str | None
    website: str | None


class EducationEntry(StrictModel):
    institution: str | None
    degree: str | None
    major: str | None
    start_date: str | None
    end_date: str | None
    gpa: str | None
    content: list[str]


class WorkExperienceEntry(StrictModel):
    company: str | None
    title: str | None
    start_date: str | None
    end_date: str | None
    location: str | None
    content: list[str]


class ResearchExperienceEntry(StrictModel):
    organization: str | None
    title: str | None
    start_date: str | None
    end_date: str | None
    location: str | None
    content: list[str]


class ProjectEntry(StrictModel):
    name: str | None
    url: str | None
    technologies: list[str]
    content: list[str]


class LanguageEntry(StrictModel):
    name: str | None
    proficiency: str | None


class PublicationEntry(StrictModel):
    title: str | None
    authors: str | None
    venue: str | None
    date: str | None
    url: str | None
    content: list[str]


class AwardEntry(StrictModel):
    name: str | None
    issuer: str | None
    date: str | None
    content: list[str]


class CertificationEntry(StrictModel):
    name: str | None
    issuer: str | None
    date: str | None
    url: str | None
    content: list[str]


class LeadershipEntry(StrictModel):
    organization: str | None
    role: str | None
    start_date: str | None
    end_date: str | None
    location: str | None
    content: list[str]


class OtherEntry(StrictModel):
    content: str


class ResumeClassification(StrictModel):
    """Exact JSON contract shared by the Foundry Agent, backend, and Review UI."""

    personal_information: PersonalInformation
    research_interests: list[str]
    education: list[EducationEntry]
    work_experience: list[WorkExperienceEntry]
    research_experience: list[ResearchExperienceEntry]
    projects: list[ProjectEntry]
    technical_skills: list[str]
    languages: list[LanguageEntry]
    publications: list[PublicationEntry]
    awards_honors: list[AwardEntry]
    certifications: list[CertificationEntry]
    leadership_activities: list[LeadershipEntry]
    other: list[OtherEntry]


class ExtractionResult(BaseModel):
    parser: str
    ocr_pages: list[int] = Field(description="One-based page numbers processed with OCR")
    characters: int
    seconds: float
    text: str


class AgentResult(BaseModel):
    name: str
    seconds: float
    validated: bool


class ResumeAnalysis(BaseModel):
    filename: str
    extraction: ExtractionResult
    agent: AgentResult
    classification: ResumeClassification
