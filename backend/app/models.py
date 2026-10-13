from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    sub: str
    name: str
    email: str
    role: Literal["candidate", "hr"]
    issuer: str


class Job(BaseModel):
    requirement_id: str
    title: str
    description: str = ""
    responsibilities: str = ""
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    qualifications: str = ""
    required_certifications: list[str] = []
    department: str = ""
    location: str = ""
    work_mode: str = ""
    employment_type: str = ""
    min_experience: float | None = None
    max_experience: float | None = None
    openings: int | None = None
    status: str = ""
    published_date: str | None = None
    deadline: str | None = None
    evaluation_criteria: dict | None = None
    rubric_version: str = "unspecified"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str = Field(min_length=1)
    resume_section: str
    project_name: str
    evidence: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_strength: str


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str
    reason: str


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(strict=True, ge=0, le=100)
    meets_minimum_criteria: bool
    match_label: str
    score_justification: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    matched_requirements: list[Evidence]
    partially_matched_requirements: list[Evidence]
    not_evidenced_requirements: list[Gap]
    evaluation_confidence: str
    relevant_evidence: list[Evidence]
    model_deployment: str = ""
    prompt_version: str = ""
    rubric_version: str = ""


class Application(BaseModel):
    application_id: str
    requirement_id: str
    job_title: str = ""
    candidate_name: str
    email: str
    applied_date: str | None = None
    hr_status: str = "Submitted"
    ai_status: str = "Pending"
    resume_file_name: str = ""
    demo_fixture: bool = False


class Candidate(Application):
    candidate_id: str
    linkedin_url: str = ""
    evaluation: Evaluation | None = None
    evaluation_date: str | None = None
    owner_sub: str = ""
    owner_issuer: str = ""
    resume_ref: str = ""

    def public_dict(self):
        return self.model_dump(exclude={"owner_sub", "owner_issuer", "resume_ref"})
