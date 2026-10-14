"""Operational diagnostics identify failed steps without logging candidate content."""

import io
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pymupdf as fitz
import pytest
from azure.core.exceptions import ServiceRequestError
from docx import Document
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import OIDC, SessionStore, require_csrf
from app.config import Settings
from app.errors import IntegrationError, ResumeValidationError
from app.models import Job
from app.services.ai import AIService
from app.services.resumes import ResumeService


@pytest.fixture(autouse=True)
def workflow_logs(caplog):
    caplog.set_level(logging.INFO, logger="app.workflow")


def event(caplog, stage, outcome):
    return any(
        f"stage={stage} " in record.getMessage() and f"outcome={outcome}" in record.getMessage()
        for record in caplog.records
    )


def private_content_absent(caplog, *values):
    for value in values:
        assert value not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_session_storage_failure_identifies_stage_without_session_or_exception_content(caplog):
    store = SessionStore(Settings(_env_file=None), redis=SimpleNamespace(get=AsyncMock()))
    store.redis.get.side_effect = RuntimeError("private-redis-password session=private-session-value")
    with pytest.raises(RuntimeError):
        await store.get("private-session-value")
    assert event(caplog, "auth.session.load", "start")
    assert event(caplog, "auth.session.load", "failed")
    private_content_absent(caplog, "private-redis-password", "private-session-value")


def test_csrf_failure_reports_validation_stage_without_logging_tokens(caplog):
    req = Request({
        "type": "http", "method": "POST", "path": "/api/applications", "query_string": b"",
        "headers": [(b"x-csrf-token", b"private-actual-token")],
        "session": {"csrf_token": "private-expected-token"}, "state": {},
    })
    with pytest.raises(HTTPException) as failure:
        require_csrf(req)
    assert failure.value.status_code == 403
    assert event(caplog, "auth.csrf.token", "rejected")
    private_content_absent(caplog, "private-actual-token", "private-expected-token")


def oidc_callback():
    settings = Settings(_env_file=None, linkedin_client_id="test", linkedin_client_secret="private-client-secret")
    oidc = OIDC(settings)
    client = SimpleNamespace(
        client_id="test",
        framework=SimpleNamespace(get_state_data=AsyncMock(return_value={
            "nonce": "private-nonce", "return_to": "/jobs/private-job-id/apply?search=private-search#private-fragment",
        })),
        authorize_access_token=AsyncMock(return_value={
            "id_token": "private-id-token", "access_token": "private-access-token",
            "userinfo": {"iss": settings.linkedin_issuer, "sub": "private-subject", "nonce": "private-nonce"},
        }),
        userinfo=AsyncMock(return_value={
            "sub": "private-subject", "name": "Private Candidate", "email": "private@example.test",
        }),
    )
    oidc.client = Mock(return_value=client)
    req = Request({
        "type": "http", "method": "GET", "path": "/auth/linkedin/callback",
        "query_string": b"code=private-auth-code&state=private-auth-state", "headers": [], "session": {}, "state": {},
    })
    return oidc, client, req


async def test_oidc_steps_and_return_template_preserve_profile_privacy(caplog):
    oidc, _, req = oidc_callback()
    user = await oidc.callback(req, "linkedin")
    assert user.name == "Private Candidate"
    for stage in ("state_load", "token_validation", "nonce_validation", "userinfo", "identity"):
        assert event(caplog, f"auth.oidc.{stage}", "completed")
    assert "/jobs/{requirement_id}/apply" in caplog.text
    assert event(caplog, "auth.oidc.session_rotation", "requested")
    private_content_absent(
        caplog, "private-", "Private Candidate", "private@example.test",
    )


async def test_oidc_userinfo_failure_reports_provider_stage_without_provider_response(caplog):
    oidc, client, req = oidc_callback()
    client.userinfo.side_effect = RuntimeError("private-provider-response secret=private-access-token")
    with pytest.raises(HTTPException) as failure:
        await oidc.callback(req, "linkedin")
    assert failure.value.status_code == 401
    assert event(caplog, "auth.oidc.userinfo", "failed")
    private_content_absent(caplog, "private-")


def ai_client(evidence="Built Python APIs."):
    row = {
        "requirement": "Python", "resume_section": "Projects", "project_name": "Portal", "evidence": evidence,
        "reason": "private-model-reason", "evidence_strength": "Strong",
    }
    assessment = {
        "score": 70, "meets_minimum_criteria": True, "match_label": "StrongEvidence",
        "score_justification": "private-model-justification", "summary": "private-model-summary",
        "matched_requirements": [row], "partially_matched_requirements": [], "not_evidenced_requirements": [],
        "evaluation_confidence": "High", "relevant_evidence": [row],
    }
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=assessment, refusal=None))])
    parse = AsyncMock(return_value=completion)
    return SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))))


async def test_ai_logs_request_validation_and_provenance_without_prompt_or_resume(caplog):
    settings = Settings(_env_file=None, azure_openai_api_key="private-openai-key")
    result = await AIService(settings, client=ai_client()).evaluate(
        "Private Candidate\nprivate@example.test\nPortal\nBuilt Python APIs.",
        Job(requirement_id="REQ1", title="Engineer", description="private-job-description", required_skills=["Python"]),
    )
    assert result.score == 70
    for stage in ("input_validation", "configuration", "identity_redaction", "provider_request", "structured_validation", "evidence_validation", "provenance"):
        assert event(caplog, f"ai.{stage}", "completed")
    private_content_absent(caplog, "private-", "private@example.test", "Private Candidate", "Built Python APIs.")


async def test_ai_rejected_quote_pinpoints_evidence_validation_without_quote(caplog):
    settings = Settings(_env_file=None, azure_openai_api_key="private-openai-key")
    with pytest.raises(IntegrationError, match="exact resume quote"):
        await AIService(settings, client=ai_client("private-hallucinated-quote")).evaluate(
            "Portal\nBuilt Python APIs.", Job(requirement_id="REQ1", title="Engineer", required_skills=["Python"]),
        )
    assert event(caplog, "ai.evidence_validation", "rejected")
    assert event(caplog, "ai.evaluate", "failed")
    assert "untraceable_resume_quote" in caplog.text
    private_content_absent(caplog, "private-", "Built Python APIs.")


def private_docx():
    document = Document()
    document.add_paragraph("private-resume-text private@example.test")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


async def test_resume_local_storage_and_extraction_log_counts_without_filename_content_or_reference(caplog, tmp_path):
    settings = Settings(_env_file=None, demo_mode=True, local_resume_dir=tmp_path / "private-path")
    service = ResumeService(settings)
    data = private_docx()
    reference = await service.store(data, "Private Candidate.docx")
    loaded = await service.read(reference)
    assert "private-resume-text" in service.extract(loaded, "Private Candidate.docx")
    await service.delete(reference)
    for stage in ("store", "upload_validation", "docx_validation", "local_write", "read", "local_read", "document_parse", "delete", "local_delete"):
        assert event(caplog, f"resume.{stage}", "completed")
    assert "bytes_count=" in caplog.text and "text_chars=" in caplog.text
    private_content_absent(caplog, "private-", "Private Candidate.docx", reference, reference.split(":", 1)[1])


def test_scanned_pdf_logs_extraction_failure_without_filename(caplog):
    with fitz.open() as document:
        document.new_page()
        data = document.tobytes()
    with pytest.raises(ResumeValidationError, match="OCR"):
        ResumeService(Settings(_env_file=None)).extract(data, "Private Candidate.pdf")
    assert event(caplog, "resume.document_parse", "rejected")
    assert event(caplog, "resume.text_extraction", "failed")
    private_content_absent(caplog, "Private Candidate.pdf")


async def test_azure_resume_failure_identifies_upload_without_storage_secrets(caplog):
    settings = Settings(_env_file=None, demo_mode=False, azure_storage_connection_string="private-storage-secret")
    blob = SimpleNamespace(upload_blob=AsyncMock(side_effect=ServiceRequestError("private-provider-message")))
    container = SimpleNamespace(
        get_container_properties=AsyncMock(return_value={"public_access": None}), get_blob_client=Mock(return_value=blob),
    )
    service = ResumeService(settings, blob_client=SimpleNamespace(get_container_client=Mock(return_value=container)))
    with pytest.raises(IntegrationError, match="storage operation failed"):
        await service.store(private_docx(), "Private Candidate.docx")
    assert event(caplog, "resume.private_container_validation", "completed")
    assert event(caplog, "resume.blob_store", "failed")
    private_content_absent(caplog, "private-", "Private Candidate.docx")


async def test_azure_container_failure_is_distinguished_from_blob_upload(caplog):
    settings = Settings(_env_file=None, demo_mode=False, azure_storage_connection_string="private-storage-secret")
    container = SimpleNamespace(
        get_container_properties=AsyncMock(side_effect=ServiceRequestError("private-container-error")),
        get_blob_client=Mock(),
    )
    service = ResumeService(settings, blob_client=SimpleNamespace(get_container_client=Mock(return_value=container)))
    with pytest.raises(IntegrationError):
        await service.store(private_docx(), "Private Candidate.docx")
    assert event(caplog, "resume.private_container_validation", "failed")
    assert not event(caplog, "resume.blob_store", "start")
    container.get_blob_client.assert_not_called()
    private_content_absent(caplog, "private-", "Private Candidate.docx")
