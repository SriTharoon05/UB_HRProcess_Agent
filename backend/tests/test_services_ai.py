import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import ConfigurationError, IntegrationError
from app.models import Job
from app.services.ai import AIService, Assessment, redact_identity, source_quote


def response(evidence="Built Python APIs.", score=73):
    row = {"requirement": "Python", "resume_section": "Projects", "project_name": "Portal", "evidence": evidence, "reason": "Explicit project implementation.", "evidence_strength": "Strong"}
    return {"score": score, "meets_minimum_criteria": False, "match_label": "PartialEvidence", "score_justification": "Python is documented in project work but Azure is not evidenced.", "summary": "Relevant project evidence; human review required.", "matched_requirements": [row], "partially_matched_requirements": [], "not_evidenced_requirements": [{"requirement": "Azure", "reason": "Not documented; absence of evidence does not establish lack of ability."}], "evaluation_confidence": "Medium", "relevant_evidence": [row]}


@pytest.fixture
def settings():
    return Settings(_env_file=None, azure_openai_api_key="test-only", azure_openai_prompt_version="v1")


def client_for(data):
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=data, refusal=None))])
    parse = AsyncMock(return_value=completion)
    return SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))), parse


async def test_full_resume_and_jd_sent_dynamic_score_kept_and_identity_minimized(settings):
    client, parse = client_for(response(score=73))
    text = "Taylor Morgan\ntaylor@example.test\n+1 555 123 4567\nSUMMARY\nAPI developer\nPROJECTS\nPortal\nBuilt Python APIs.\nLAST SECTION\nAccessibility achievements."
    job = Job(requirement_id="REQ-1", title="API Engineer", description="Full job description.", responsibilities="Develop APIs.", required_skills=["Python"], preferred_skills=["Azure"], qualifications="Relevant education.", required_certifications=["Optional credential"], rubric_version="job-v2")
    result = await AIService(settings, client=client).evaluate(text, job)
    assert result.score == 73
    assert result.prompt_version == "v1"
    assert result.rubric_version == "job-v2"
    kwargs = parse.call_args.kwargs
    assert kwargs["temperature"] == 0.1
    assert kwargs["response_format"] is Assessment
    document = json.loads(kwargs["messages"][1]["content"])
    assert "Taylor Morgan" not in document["RESUME"]
    assert "taylor@example.test" not in document["RESUME"]
    assert "+1 555 123 4567" not in document["RESUME"]
    assert "LAST SECTION\nAccessibility achievements." in document["RESUME"]
    assert document["JOB"]["description"] == "Full job description."
    assert document["JOB"]["responsibilities"] == "Develop APIs."
    assert document["JOB"]["qualifications"] == "Relevant education."


async def test_hallucinated_evidence_rejected_and_score_never_defaulted(settings):
    client, _ = client_for(response("Built Azure architecture."))
    with pytest.raises(IntegrationError, match="exact resume quote"):
        await AIService(settings, client=client).evaluate("Portal\nBuilt Python APIs.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))
    data = response()
    data["matched_requirements"][0]["project_name"] = "Invented project"
    client, _ = client_for(data)
    with pytest.raises(IntegrationError, match="project name"):
        await AIService(settings, client=client).evaluate("Portal\nBuilt Python APIs.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))


@pytest.mark.parametrize("score", [-1, 101, 73.2, "73", True])
def test_structured_schema_rejects_non_integer_and_out_of_range_score(score):
    with pytest.raises(ValidationError):
        Assessment.model_validate(response(score=score))


async def test_no_evidence_cannot_receive_positive_score(settings):
    data = response()
    data["matched_requirements"] = []
    data["relevant_evidence"] = []
    client, _ = client_for(data)
    with pytest.raises(IntegrationError, match="without any traceable"):
        await AIService(settings, client=client).evaluate("No relevant job text.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))


async def test_missing_config_empty_input_refusal_and_unknown_prompt(settings):
    job = Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"])
    with pytest.raises(IntegrationError, match="no readable text"):
        await AIService(settings).evaluate("   ", job)
    settings.azure_openai_api_key = ""
    with pytest.raises(ConfigurationError, match="API key"):
        await AIService(settings).evaluate("Resume text", job)
    settings.azure_openai_api_key = "test-only"
    settings.azure_openai_prompt_version = "v99"
    with pytest.raises(ConfigurationError, match="not installed"):
        await AIService(settings).evaluate("Resume text", job)
    settings.azure_openai_prompt_version = "v1"
    client, _ = client_for(None)
    with pytest.raises(IntegrationError, match="valid structured evaluation"):
        await AIService(settings, client=client).evaluate("Resume text", job)


def test_redaction_preserves_skills_and_work_content():
    text = "PROJECTS\nPortal\nBuilt Python APIs in 2020.\nGender: irrelevant\nhttps://linkedin.com/in/example\nSkills: Python, React\nEmployment 2019-2023\nEarlier role 2018 - 2022\nPhone: 555-1234\nProcessed 10000000000 records\nRoles in 2018 - 2022 - 2024"
    redacted = redact_identity(text)
    assert "PROJECTS\nPortal\nBuilt Python APIs in 2020." in redacted
    assert "irrelevant" not in redacted
    assert "linkedin.com" not in redacted
    assert "Skills: Python, React" in redacted
    assert "Employment 2019-2023" in redacted
    assert "Earlier role 2018 - 2022" in redacted
    assert "555-1234" not in redacted
    assert "Processed 10000000000 records" in redacted
    assert "Roles in 2018 - 2022 - 2024" in redacted
    assert redact_identity("Software Engineer\nWork history") == "Software Engineer\nWork history"


async def test_job_title_alone_cannot_receive_ai_score(settings):
    client, parse = client_for(response())
    with pytest.raises(IntegrationError, match="job title alone"):
        await AIService(settings, client=client).evaluate("Built Python APIs.", Job(requirement_id="REQ-1", title="Engineer"))
    parse.assert_not_awaited()


async def test_oversized_resume_fails_instead_of_truncating(settings):
    settings.azure_openai_max_resume_chars = 10
    client, parse = client_for(response())
    with pytest.raises(IntegrationError, match="No text was truncated"):
        await AIService(settings, client=client).evaluate("Complete resume with extensive projects.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))
    parse.assert_not_awaited()


@pytest.mark.parametrize("quote,source,expected", [
    ("Built Python APIs.", "Portal\nBuilt Python\n    APIs.", "Built Python\n    APIs."),
    ("Built Python APIs.", "Built Python\u00a0APIs.", "Built Python\u00a0APIs."),
    ("Built Azure APIs.", "Built Python APIs.", ""),
    ("3 years", "13 years", ""),
    ("Built APIs", "Built APIsExtra", ""),
    ("Built ... APIs.", "Built Python APIs.", ""),
    ("Built APIs.", "Built APIs.", "Built APIs."),
])
def test_source_quotes_only_allow_whitespace_and_preserve_original_span(quote, source, expected):
    assert source_quote(quote, source) == expected


async def test_pdf_line_wrapping_is_restored_in_saved_evidence(settings):
    client, parse = client_for(response())
    result = await AIService(settings, client=client).evaluate(
        "Portal\nBuilt Python\n   APIs.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))
    assert result.score == 73
    assert result.matched_requirements[0].evidence == "Built Python\n   APIs."
    parse.assert_awaited_once()


async def test_invalid_evidence_gets_bounded_correction_with_full_original_inputs(settings):
    client, parse = client_for(None)
    def completion(data):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=data, refusal=None))])
    parse.side_effect = [completion(response("Invented implementation.")), completion(response(score=64))]
    result = await AIService(settings, client=client).evaluate(
        "Portal\nBuilt Python APIs.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))
    assert result.score == 64 and parse.await_count == 2
    first, second = [call.kwargs["messages"] for call in parse.await_args_list]
    assert first[1] == second[1] and len(first) == 2 and len(second) == 3
    assert "Invented implementation" not in second[-1]["content"]
    assert "contiguous quote" in second[-1]["content"]


async def test_repeated_invalid_output_stops_at_configured_limit(settings):
    settings.azure_openai_validation_attempts = 2
    client, parse = client_for(response("Invented implementation."))
    with pytest.raises(IntegrationError, match="exact resume quote"):
        await AIService(settings, client=client).evaluate(
            "Portal\nBuilt Python APIs.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))
    assert parse.await_count == 2


async def test_weak_match_with_zero_score_and_explained_gaps_is_valid(settings):
    data = response(score=0)
    data.update(matched_requirements=[], relevant_evidence=[], match_label="InsufficientEvidence")
    client, parse = client_for(data)
    result = await AIService(settings, client=client).evaluate(
        "Office administration and spreadsheet reporting.", Job(requirement_id="REQ-1", title="Engineer", required_skills=["Python"]))
    assert result.score == 0 and result.match_label == "InsufficientEvidence" and result.not_evidenced_requirements
    parse.assert_awaited_once()
