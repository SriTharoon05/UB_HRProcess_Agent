"""Actual Azure OpenAI evaluation, distinct from the labeled demo fixtures."""

from __future__ import annotations

import json
import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Literal

from openai import APIConnectionError, APIStatusError, AsyncAzureOpenAI, APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.errors import ConfigurationError, IntegrationError
from app.models import Evaluation, Job
from app.observability import log_event, traced


class QuotedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requirement: str = Field(min_length=1)
    resume_section: str = Field(min_length=1)
    project_name: str
    evidence: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_strength: Literal["Strong", "Partial", "Weak"]


class EvidenceGap(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requirement: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class Assessment(BaseModel):
    """Only model-generated fields. Provenance is supplied by the backend."""
    model_config = ConfigDict(extra="forbid", strict=True)
    score: int = Field(ge=0, le=100)
    meets_minimum_criteria: bool
    match_label: Literal["StrongEvidence", "PartialEvidence", "InsufficientEvidence"]
    score_justification: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    matched_requirements: list[QuotedEvidence]
    partially_matched_requirements: list[QuotedEvidence]
    not_evidenced_requirements: list[EvidenceGap]
    evaluation_confidence: Literal["High", "Medium", "Low"]
    relevant_evidence: list[QuotedEvidence]


@traced("ai.identity_redaction")
def redact_identity(text: str) -> str:
    """Conservatively minimize obvious identifiers while retaining all work/project text.

    This is best-effort minimization, not an anonymization guarantee. Names embedded in
    narrative may remain. Quotes are validated against this exact input and the original.
    """
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[email removed]", text, flags=re.I)
    text = re.sub(r"https?://(?:www\.)?linkedin\.com/[^\s]+", "[profile removed]", text, flags=re.I)
    text = re.sub(r"(?im)^\s*(?:phone|mobile|telephone|contact number)\s*:\s*[^\n]+", "[phone removed]", text)
    # Require at least 10 digits, preserving employment ranges such as 2018 - 2022.
    def remove_phone(match: re.Match) -> str:
        value = match.group(0)
        if len(re.sub(r"\D", "", value)) < 10 or re.fullmatch(r"\d{4}[- /]\d{2}[- /]\d{2}", value):
            return value
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        surrounding_line = text[line_start:line_end if line_end >= 0 else len(text)].strip()
        telephone_shape = value.startswith("+") or "(" in value or bool(re.fullmatch(r"\d{3}[ .-]\d{3}[ .-]\d{4}", value))
        return "[phone removed]" if telephone_shape or surrounding_line == value.strip() else value

    text = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)", remove_phone, text)
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Only a plausible name at the beginning, or explicitly labeled identifiers.
        role_words = {"engineer", "developer", "architect", "manager", "scientist", "analyst", "designer", "recruiter", "operations", "consultant", "professional", "technical", "curriculum", "vitae", "resume", "summary", "experience", "project", "projects", "education", "certifications", "skills"}
        if index < 3 and not role_words.intersection(stripped.lower().split()) and re.fullmatch(r"(?:[A-Z][a-z]+[ '-]){1,3}[A-Z][a-z]+", stripped):
            lines[index] = "[name removed]\n"
        break
    for index, line in enumerate(lines):
        if re.match(r"^\s*(?:name|date of birth|dob|gender|nationality|marital status|address)\s*:", line, re.I):
            lines[index] = "[personal information removed]\n"
    redacted = "".join(lines)
    log_event("ai.identity_redaction", "validated", text_chars=len(redacted))
    return redacted


@traced("ai.evidence_validation")
def validate_evidence(assessment: Assessment, resume: str, original: str) -> None:
    evidence_rows = assessment.matched_requirements + assessment.partially_matched_requirements + assessment.relevant_evidence
    for index, item in enumerate(evidence_rows):
        # PDF layout often wraps sentences and DOCX can contain nonbreaking spaces.
        # Match whitespace only, then save the exact original source span. Never
        # accept paraphrases, fuzzy similarity, changed numbers or omitted words.
        quote = source_quote(item.evidence, original)
        if not quote or not source_quote(item.evidence, resume):
            log_event("ai.evidence_validation", "rejected", level=logging.WARNING, reason="untraceable_resume_quote", count=index, validated=False)
            raise EvidenceValidationError("untraceable_resume_quote", "AI returned supporting evidence that is not an exact resume quote")
        project = source_quote(item.project_name, original) if item.project_name else ""
        if item.project_name and (not project or not source_quote(item.project_name, resume)):
            log_event("ai.evidence_validation", "rejected", level=logging.WARNING, reason="project_not_in_resume", count=index, validated=False)
            raise EvidenceValidationError("project_not_in_resume", "AI returned a project name that is not present in the resume")
        item.evidence = quote
        item.project_name = project
    if assessment.score > 0 and not evidence_rows:
        log_event("ai.evidence_validation", "rejected", level=logging.WARNING, reason="positive_score_without_evidence", validated=False)
        raise EvidenceValidationError("positive_score_without_evidence", "AI assigned an evidence score without any traceable supporting evidence")
    log_event("ai.evidence_validation", "validated", count=len(evidence_rows), validated=True)


class EvidenceValidationError(IntegrationError):
    def __init__(self, reason: str, message: str):
        super().__init__(message, retryable=False)
        self.reason = reason


def source_quote(quote: str, source: str) -> str:
    """Recover a contiguous source span allowing only whitespace differences."""
    normalized_quote = " ".join(quote.split())
    if not normalized_quote:
        return ""
    # One pass maps normalized characters back to their original offsets.
    characters, offsets = [], []
    for index, character in enumerate(source):
        if character.isspace():
            if characters and characters[-1] != " ":
                characters.append(" ")
                offsets.append(index)
        else:
            characters.append(character)
            offsets.append(index)
    normalized_source = "".join(characters)
    start = normalized_source.find(normalized_quote)
    while start >= 0:
        end = start + len(normalized_quote)
        # Do not turn a fragment of a word or number into evidence.
        before = start == 0 or not (normalized_source[start - 1].isalnum() and normalized_quote[0].isalnum())
        after = end == len(normalized_source) or not (normalized_source[end].isalnum() and normalized_quote[-1].isalnum())
        if before and after:
            return source[offsets[start]:offsets[end - 1] + 1]
        start = normalized_source.find(normalized_quote, start + 1)
    return ""


CORRECTION_RULES = {
    "untraceable_resume_quote": "At least one evidence quote was not a contiguous quote from RESUME. Copy the exact text, preserving words, punctuation and numbers. Do not paraphrase, combine separate passages or use ellipses. Put unsupported requirements in not_evidenced_requirements.",
    "project_not_in_resume": "At least one project_name was absent from RESUME. Copy a project title present in RESUME or use an empty project_name.",
    "positive_score_without_evidence": "A positive score was returned with all supporting evidence lists empty. Reassess JOB against RESUME and include actual supporting quotes. If no job-related supporting evidence exists, return score 0, InsufficientEvidence and meets_minimum_criteria false, with explained gaps. A weak match is a valid assessment.",
    "structured_output_invalid": "Return a complete response matching the required schema and types. Include supported quotes, explained gaps and an evidence-based integer score between 0 and 100.",
}


class AIService:
    def __init__(self, settings: Any, *, client: Any = None):
        self.settings = settings
        self.client = client

    @traced("ai.evaluate")
    async def evaluate(self, resume_text: str, job: Job) -> Evaluation:
        log_event("ai.input_validation", "start", text_chars=len(resume_text))
        if not resume_text.strip():
            log_event("ai.input_validation", "rejected", level=logging.WARNING, reason="resume_text_empty")
            raise IntegrationError("Resume has no readable text; AI evaluation cannot proceed", retryable=False)
        maximum = getattr(self.settings, "azure_openai_max_resume_chars", 100000)
        if len(resume_text) > maximum:
            log_event("ai.input_validation", "rejected", level=logging.WARNING, reason="resume_context_limit", text_chars=len(resume_text))
            raise IntegrationError("Complete resume exceeds AZURE_OPENAI_MAX_RESUME_CHARS; increase the configured limit only if the deployment context allows it. No text was truncated.", retryable=False)
        if not any([job.description.strip(), job.responsibilities.strip(), job.required_skills, job.qualifications.strip()]):
            log_event("ai.input_validation", "rejected", level=logging.WARNING, reason="job_requirements_missing")
            raise IntegrationError("Job description and evaluation requirements are missing; a job title alone cannot be evaluated", retryable=False)
        log_event("ai.input_validation", "completed", validated=True)
        log_event("ai.configuration", "start")
        required = ("azure_openai_endpoint", "azure_openai_api_key", "azure_openai_deployment", "azure_openai_api_version")
        for field in required:
            log_event("ai.configuration.check", "completed", field=field, configured=bool(getattr(self.settings, field, "")))
        if any(not getattr(self.settings, field, "") for field in required):
            log_event("ai.configuration", "failed", level=logging.ERROR, reason="required_settings_missing")
            raise ConfigurationError("Azure OpenAI endpoint, API key, deployment, and API version are required.")
        version = self.settings.azure_openai_prompt_version
        if not re.fullmatch(r"v\d+", version):
            log_event("ai.configuration", "failed", level=logging.ERROR, reason="prompt_version_invalid")
            raise ConfigurationError("AZURE_OPENAI_PROMPT_VERSION must reference an installed versioned prompt.")
        prompt_path = Path(__file__).parent / "prompts" / f"evaluation_{version}.txt"
        if not prompt_path.is_file():
            log_event("ai.configuration", "failed", level=logging.ERROR, reason="prompt_not_installed")
            raise ConfigurationError(f"Evaluation prompt {version} is not installed.")
        log_event("ai.configuration", "completed", deployment=self.settings.azure_openai_deployment, prompt_version=version)
        # Nothing truncates the JD or resume. Context-window errors are explicit failures.
        resume = redact_identity(resume_text)
        job_data = job.model_dump(mode="json")
        messages = [
            {"role": "system", "content": prompt_path.read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps({"JOB": job_data, "RESUME": resume}, ensure_ascii=False)},
        ]
        log_event("ai.prompt_preparation", "completed", text_chars=len(resume), count=len(messages), prompt_version=version)

        @traced("ai.provider_request")
        async def perform(client: Any, attempt: int) -> Assessment:
            try:
                completion = await client.beta.chat.completions.parse(
                    model=self.settings.azure_openai_deployment,
                    messages=[dict(message) for message in messages],
                    temperature=0.1,
                    response_format=Assessment,
                )
                log_event("ai.provider_response", "received", count=len(completion.choices), attempt=attempt)
                log_event("ai.structured_validation", "start")
                message = completion.choices[0].message
                if getattr(message, "refusal", None) or getattr(message, "parsed", None) is None:
                    log_event("ai.structured_validation", "rejected", level=logging.WARNING, reason="refusal_or_missing_structured_output")
                    raise IntegrationError("Azure OpenAI did not provide a valid structured evaluation", retryable=False)
                assessment = Assessment.model_validate(message.parsed)
                log_event("ai.structured_validation", "completed", validated=True)
                validate_evidence(assessment, resume, resume_text)
                return assessment
            except (APIConnectionError, APITimeoutError) as exc:
                log_event("ai.provider_request", "failed", level=logging.WARNING, exception_type=type(exc).__name__, retryable=True)
                raise IntegrationError("Azure OpenAI connection failed") from exc
            except APIStatusError as exc:
                log_event("ai.provider_request", "failed", level=logging.WARNING, status_code=exc.status_code, exception_type=type(exc).__name__, retryable=exc.status_code in {408, 429} or exc.status_code >= 500)
                raise IntegrationError(
                    f"Azure OpenAI request failed (HTTP {exc.status_code}); verify deployment and structured-output support",
                    retryable=exc.status_code in {408, 429} or exc.status_code >= 500,
                ) from exc
            except (ValidationError, ValueError, IndexError) as exc:
                log_event("ai.structured_validation", "failed", level=logging.WARNING, exception_type=type(exc).__name__, validated=False)
                raise EvidenceValidationError("structured_output_invalid", "Azure OpenAI response failed structured validation") from exc

        async def validated_assessment(client: Any) -> Assessment:
            maximum_attempts = getattr(self.settings, "azure_openai_validation_attempts", 3)
            for attempt in range(1, maximum_attempts + 1):
                log_event("ai.validation_attempt", "start", attempt=attempt, max_attempts=maximum_attempts)
                try:
                    result = await perform(client, attempt)
                    log_event("ai.validation_attempt", "completed", attempt=attempt, validated=True)
                    return result
                except EvidenceValidationError as exc:
                    log_event("ai.validation_attempt", "failed", level=logging.WARNING, attempt=attempt,
                              max_attempts=maximum_attempts, reason=exc.reason, retryable=attempt < maximum_attempts)
                    if attempt == maximum_attempts:
                        raise
                    # Feedback contains only fixed validation instructions. Keep
                    # the original JD and resume; never log model/candidate text.
                    messages.append({"role": "user", "content": "The previous response failed validation. " + CORRECTION_RULES[exc.reason] + " Re-evaluate the original JOB and RESUME and return the complete corrected assessment."})
            raise IntegrationError("AI validation attempt limit is invalid", retryable=False)

        async def timed_assessment(client: Any) -> Assessment:
            try:
                # Leave room inside ARQ's 540-second limit for extraction,
                # state persistence and the D365 write, including SDK retries.
                return await asyncio.wait_for(validated_assessment(client), timeout=360)
            except TimeoutError:
                log_event("ai.evaluate", "failed", level=logging.WARNING, reason="evaluation_time_limit")
                raise IntegrationError("AI evaluation exceeded its time limit. HR can retry the application.", retryable=False) from None

        if self.client is not None:
            assessment = await timed_assessment(self.client)
        else:
            async with AsyncAzureOpenAI(
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_key=self.settings.azure_openai_api_key,
                api_version=self.settings.azure_openai_api_version,
                timeout=90.0,
                max_retries=2,
            ) as client:
                assessment = await timed_assessment(client)
        log_event("ai.provenance", "start", deployment=self.settings.azure_openai_deployment, prompt_version=version)
        result = Evaluation.model_validate({
            **assessment.model_dump(),
            "model_deployment": self.settings.azure_openai_deployment,
            "prompt_version": version,
            "rubric_version": job.rubric_version,
        })
        log_event("ai.provenance", "completed", validated=True, deployment=self.settings.azure_openai_deployment, prompt_version=version)
        return result
