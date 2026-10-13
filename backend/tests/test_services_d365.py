import json
from unittest.mock import Mock

import httpx
import pytest

from app.config import Settings
from app.errors import ConfigurationError, IntegrationError
from app.models import User
from app.services.d365 import D365Service, normalize


@pytest.fixture
def settings():
    return Settings(_env_file=None, d365_enabled=True, d365_tenant_id="tenant-id", d365_client_id="client-id", d365_client_secret="test-only", d365_save_evaluation_path="/save", d365_top_candidates_path="/top", d365_my_applications_path="/mine", d365_application_path="/application")


@pytest.fixture
def msal_app():
    return Mock(acquire_token_for_client=Mock(return_value={"access_token": "unit-test-token", "expires_in": 3600}))


def evaluation(score=73):
    evidence = {"requirement": "Python", "resume_section": "Projects", "project_name": "Portal", "evidence": "Built Python APIs.", "reason": "Direct implementation evidence.", "evidence_strength": "Strong"}
    return {"score": score, "meets_minimum_criteria": False, "match_label": "PartialEvidence", "score_justification": "Python is demonstrated; cloud work is not evidenced.", "summary": "Relevant API work, incomplete cloud evidence.", "matched_requirements": [evidence], "partially_matched_requirements": [], "not_evidenced_requirements": [{"requirement": "Azure", "reason": "Not documented."}], "relevant_evidence": [evidence], "evaluation_confidence": "Medium", "model_deployment": "test-model", "prompt_version": "v1", "rubric_version": "v1"}


def candidate(application_id="APP-1", score=73):
    return {"ApplicationId": application_id, "CandidateId": "CAN-1", "RequirementId": "REQ-1", "JobTitle": "Engineer", "CandidateName": "Test Candidate", "Email": "test@example.test", "LinkedInIssuer": "issuer", "LinkedInSub": "subject", "ResumeBlobKey": "azure:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf", "Evaluation": evaluation(score)}


async def test_token_reused_and_failure_does_not_invent_token(settings, msal_app):
    service = D365Service(settings, msal_app=msal_app)
    assert await service.get_access_token() == await service.get_access_token()
    msal_app.acquire_token_for_client.assert_called_once_with(scopes=[f"{settings.d365_base_url}/.default"])
    msal_app.acquire_token_for_client.return_value = {"error": "invalid_client", "error_description": "secret diagnostic"}
    with pytest.raises(IntegrationError, match="authentication failed") as error:
        await service.get_access_token(force_refresh=True)
    assert "secret diagnostic" not in str(error.value)


async def test_parameterless_existing_endpoint_and_custom_request_mapping(settings, msal_app):
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if request.url.path.endswith("getOpenRequirements"):
            return httpx.Response(200, json={"Requirements": [{"RequirementId": "REQ-1", "JobTitle": "Engineer", "JobStatus": "Open", "RequiredSkills": "Python, React"}, {"RequirementId": "REQ-closed", "JobTitle": "Closed", "JobStatus": "Closed"}]})
        return httpx.Response(200, json={"Success": True, "ApplicationId": "APP-1"})
    settings.d365_request_wrappers = {"submit_application": "contract"}
    settings.d365_request_field_maps = {"submit_application": {"requirement_id": "Vacancy"}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = D365Service(settings, client=client, msal_app=msal_app)
        jobs = await service.get_open_requirements()
        assert [j.requirement_id for j in jobs] == ["REQ-1"]
        assert jobs[0].required_skills == ["Python", "React"]
        result = await service.submit_application({"requirement_id": "REQ-1", "owner_sub": "subject"})
    assert result["application_id"] == "APP-1"
    assert calls == [{}, {"contract": {"Company": "DAT", "Vacancy": "REQ-1", "LinkedInSub": "subject"}}]


async def test_submit_requires_stable_id_and_explicit_success(settings, msal_app):
    for response in [{"Success": True}, {"ApplicationId": "APP-1"}, {"Success": False, "ApplicationId": "APP-1"}]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))) as client:
            with pytest.raises(IntegrationError):
                await D365Service(settings, client=client, msal_app=msal_app).submit_application({"requirement_id": "REQ-1"})


async def test_missing_pending_endpoints_do_not_call_auth(settings, msal_app):
    settings.d365_save_evaluation_path = ""
    settings.d365_top_candidates_path = ""
    service = D365Service(settings, msal_app=msal_app)
    with pytest.raises(ConfigurationError, match="D365_SAVE_EVALUATION_PATH"):
        await service.save_candidate_evaluation({"application_id": "APP-1", "evaluation": evaluation()})
    with pytest.raises(ConfigurationError, match="D365_TOP_CANDIDATES_PATH"):
        await service.get_top_candidates("REQ-1")
    msal_app.acquire_token_for_client.assert_not_called()


async def test_save_preserves_score_serializes_memos_and_checks_ack(settings, msal_app):
    calls = []
    def handler(request):
        calls.append((json.loads(request.content), request.headers["Idempotency-Key"]))
        return httpx.Response(200, json={"Success": True, "ApplicationId": "APP-1"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await D365Service(settings, client=client, msal_app=msal_app).save_candidate_evaluation({"application_id": "APP-1", "evaluation": evaluation(73)})
    body, key = calls[0]
    assert key == "evaluation:APP-1"
    assert body["_request"]["Score"] == 73
    assert json.loads(body["_request"]["MatchedSkillsJson"])[0]["Evidence"] == "Built Python APIs."
    assert json.loads(body["_request"]["MissingSkillsJson"])[0]["Requirement"] == "Azure"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"Success": True, "ApplicationId": "WRONG"}))) as client:
        with pytest.raises(IntegrationError, match="wrong ApplicationId"):
            await D365Service(settings, client=client, msal_app=msal_app).save_candidate_evaluation({"application_id": "APP-1", "evaluation": evaluation()})


async def test_new_evaluation_write_requires_known_model_provenance(settings, msal_app):
    data = evaluation()
    data["model_deployment"] = ""
    with pytest.raises(IntegrationError, match="actual model deployment"):
        await D365Service(settings, msal_app=msal_app).save_candidate_evaluation({"application_id": "APP-1", "evaluation": data})
    msal_app.acquire_token_for_client.assert_not_called()


def test_response_memo_normalization_and_field_override():
    output = normalize({"VacancyNumber": "REQ-1", "MatchedSkillsJson": '[{"Requirement":"Python","ResumeSection":"Projects","Evidence":"Built Python APIs."}]', "AIStatus": "Completed"}, {"requirement_id": "VacancyNumber"})
    assert output["requirement_id"] == "REQ-1"
    assert output["matched_requirements"][0]["resume_section"] == "Projects"
    assert output["ai_status"] == "Completed"
    with pytest.raises(IntegrationError, match="malformed evaluation JSON"):
        normalize({"EvidenceJson": "not json"})


def test_optional_contract_fields_can_be_omitted(settings):
    settings.d365_request_field_maps = {"submit_application": {"consent_accepted": ""}}
    body = D365Service(settings)._body("submit_application", {"job_description_hash": "abc", "consent_accepted": True})
    assert body == {"_request": {"JDHash": "abc"}}


async def test_submit_profile_snapshot_stays_separate_from_confirmed_contact_and_serializes_oidc_keys(settings, msal_app):
    calls = []
    profile = {
        "sub": "subject",
        "issuer": "https://www.linkedin.com/oauth",
        "name": "Provider Applicant",
        "given_name": "Provider",
        "family_name": "Applicant",
        "email": "provider@example.test",
        "email_verified": False,
        "picture": "https://media.example.test/profile.png",
        "locale": "en_IN",
    }

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"Success": True, "ApplicationId": "APP-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await D365Service(settings, client=client, msal_app=msal_app).submit_application({
            "requirement_id": "REQ-1",
            "owner_issuer": profile["issuer"],
            "owner_sub": profile["sub"],
            "candidate_name": "Confirmed Applicant",
            "email": "confirmed@example.test",
            "phone": "+91 555 0100",
            "linkedin_url": "https://www.linkedin.com/in/confirmed-applicant",
            "linkedin_profile": profile,
        })
    body = calls[0]["_request"]
    assert body["FullName"] == "Confirmed Applicant"
    assert body["Email"] == "confirmed@example.test"
    assert body["LinkedInIssuer"] == profile["issuer"] and body["LinkedInSub"] == profile["sub"]
    assert body["Phone"] == "+91 555 0100"
    assert body["LinkedInUrl"] == "https://www.linkedin.com/in/confirmed-applicant"
    assert json.loads(body["LinkedInProfileJson"]) == profile
    assert normalize({"LinkedInProfileJson": body["LinkedInProfileJson"]})["linkedin_profile"] == profile
    assert "Score" not in body and "Evaluation" not in body


def test_profile_contract_can_be_renamed_or_omitted_and_rejects_private_token_fields(settings):
    profile = {"sub": "subject", "issuer": "https://www.linkedin.com/oauth", "name": None}
    settings.d365_request_field_maps = {"submit_application": {"linkedin_profile": "ProviderProfileJson"}}
    body = D365Service(settings)._body("submit_application", {"linkedin_profile": profile})
    assert json.loads(body["_request"]["ProviderProfileJson"]) == {"sub": "subject", "issuer": profile["issuer"]}
    settings.d365_request_field_maps = {"submit_application": {"linkedin_profile": ""}}
    assert D365Service(settings)._body("submit_application", {"linkedin_profile": profile}) == {"_request": {}}
    settings.d365_request_field_maps = {}
    with pytest.raises(IntegrationError, match="Only permitted LinkedIn profile fields") as error:
        D365Service(settings)._body("submit_application", {"linkedin_profile": {**profile, "access_token": "private-sentinel"}})
    assert "private-sentinel" not in str(error.value)
    with pytest.raises(IntegrationError, match="malformed profile JSON"):
        normalize({"LinkedInProfileJson": "not JSON"})


async def test_hr_ranking_scoped_to_requirement_and_owned_history(settings, msal_app):
    rows = [candidate("APP-LOW", 52), candidate("APP-HIGH", 91)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"Candidates": rows}))) as client:
        ranked = await D365Service(settings, client=client, msal_app=msal_app).get_top_candidates("REQ-1", 1)
        assert ranked[0].application_id == "APP-HIGH"
    rows[0]["RequirementId"] = "UNRELATED"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"Candidates": rows}))) as client:
        with pytest.raises(IntegrationError, match="different requirement"):
            await D365Service(settings, client=client, msal_app=msal_app).get_top_candidates("REQ-1")
    user = User(sub="subject", issuer="issuer", name="Test", email="test@example.test", role="candidate")
    own = candidate()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"Applications": [own]}))) as client:
        records = await D365Service(settings, client=client, msal_app=msal_app).get_my_applications(user)
        assert records[0].owner_sub == user.sub
    own["LinkedInSub"] = "other-subject"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"Applications": [own]}))) as client:
        with pytest.raises(IntegrationError, match="ownership"):
            await D365Service(settings, client=client, msal_app=msal_app).get_my_applications(user)


async def test_proposed_top_candidates_contract_accepts_missing_optional_provenance(settings, msal_app):
    row = {
        "CandidateId": "CAN-1", "CandidateName": "Test Candidate", "Email": "test@example.test",
        "ApplicationId": "APP-1", "RequirementId": "REQ-1", "Score": 92,
        "MatchLabel": "StrongEvidence", "ScoreJustification": "Strong documented API work.",
        "Summary": "Relevant implementation evidence.", "MatchedSkillsJson": "[]",
        "PartiallyMatchedJson": "[]", "MissingSkillsJson": "[]", "EvidenceJson": "[]",
        "EvaluationConfidence": "High", "MeetsMinimumCriteria": True,
        "AIStatus": "Completed", "HRStatus": "New", "ResumeFileName": "resume.pdf",
        "ResumeBlobKey": "azure:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"Candidates": [row]}))) as client:
        records = await D365Service(settings, client=client, msal_app=msal_app).get_top_candidates("REQ-1")
    assert records[0].evaluation.score == 92
    assert records[0].job_title == ""
    assert records[0].evaluation.model_deployment == ""
    assert records[0].evaluation.prompt_version == ""
    assert records[0].evaluation.rubric_version == ""


async def test_401_refresh_and_safe_service_errors(settings, msal_app):
    statuses = iter([401, 200])
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(next(statuses), json={"Requirements": []}))) as client:
        assert await D365Service(settings, client=client, msal_app=msal_app).get_open_requirements() == []
    assert msal_app.acquire_token_for_client.call_count == 2
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403, json={"private": "provider secret"}))) as client:
        with pytest.raises(IntegrationError) as error:
            await D365Service(settings, client=client, msal_app=msal_app).get_open_requirements()
        assert error.value.retryable is False
        assert "provider secret" not in str(error.value)
