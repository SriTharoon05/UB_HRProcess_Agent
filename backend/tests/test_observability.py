"""Trace failures and concurrent requests without printing private inputs."""

import asyncio
import io
import logging
import os
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import Mock

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import DemoAdapter
from app.main import create_app
from app.observability import SafeAccessLogs, SafeExceptionLogs, SafeSDKLogs, log_context, log_event, log_request_shape, traced
from app.queue import SubmissionCoordinator
from app.services.sqlite_d365 import SQLiteD365Service


def events(caplog):
    return [record.workflow_event for record in caplog.records if hasattr(record, "workflow_event")]


async def test_parallel_tasks_keep_distinct_context_and_failure_location_without_exception_value(caplog):
    caplog.set_level(logging.INFO, logger="app.workflow")
    first, second = str(uuid.uuid4()), str(uuid.uuid4())

    @traced("test.provider")
    async def operation(fails):
        await asyncio.sleep(0)
        log_event("test.provider", "received", email="private@example.test", token="private-token")
        if fails:
            raise ValueError("private-token private@example.test")

    async def task(request_id, fails):
        with log_context(request_id=request_id, application_id="APP-test", owner_sub="private-sub"):
            await operation(fails)

    results = await asyncio.gather(task(first, True), task(second, False), return_exceptions=True)
    assert isinstance(results[0], ValueError) and results[1] is None
    failures = [event for event in events(caplog) if event["outcome"] == "failed"]
    assert len(failures) == 1 and failures[0]["request_id"] == first
    assert failures[0]["exception_type"] == "ValueError" and failures[0]["elapsed_ms"] >= 0
    assert "test_observability.py:" in failures[0]["code_location"]
    assert any(event["outcome"] == "completed" and event["request_id"] == second for event in events(caplog))
    log_event("test.after", "completed")
    assert "request_id" not in events(caplog)[-1]
    assert "private" not in caplog.text


async def test_concurrent_http_requests_keep_reference_and_safe_route_template(caplog):
    caplog.set_level(logging.INFO, logger="app.workflow")
    application = create_app(Settings(_env_file=None, public_rate_limit=999))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        responses = await asyncio.gather(client.get("/api/health?code=private-code"),
                                         client.get("/api/jobs/private-personal-id?search=private-contact"))
    ids = [str(uuid.UUID(response.headers["x-request-id"])) for response in responses]
    assert len(set(ids)) == 2 and [response.status_code for response in responses] == [200, 404]
    request_events = [event for event in events(caplog) if event["stage"] == "http.request"]
    for request_id in ids:
        matching = [event for event in request_events if event["request_id"] == request_id]
        assert matching[0]["outcome"] == "start" and matching[-1]["status_code"] in {200, 404}
        assert matching[-1]["elapsed_ms"] >= 0
    assert any(event["route"] == "/api/jobs/{requirement_id}" for event in request_events)
    assert "private-code" not in caplog.text and "private-contact" not in caplog.text


def test_pre_route_upload_rejection_and_unexpected_failure_have_references(caplog, tmp_path):
    caplog.set_level(logging.INFO, logger="app.workflow")
    application = create_app(Settings(_env_file=None, max_resume_size_mb=1, local_resume_dir=tmp_path))

    @application.get("/test-failure")
    async def failure():
        raise RuntimeError("private-provider-body private@example.test")

    with TestClient(application, raise_server_exceptions=False) as client:
        rejected = client.post("/api/applications", content=b"x" * (2 * 1024 * 1024 + 1))
        assert rejected.status_code == 413
        reference = rejected.headers["x-request-id"]
        assert any(event["stage"] == "upload.receive" and event["outcome"] == "failed"
                   and event["request_id"] == reference for event in events(caplog))
        failed = client.get("/test-failure")
        assert failed.status_code == 503
        reference = failed.headers["x-request-id"]
        assert any(event["stage"] == "http.unexpected" and event["exception_type"] == "RuntimeError"
                   and event["request_id"] == reference for event in events(caplog))
    assert "private-provider-body" not in caplog.text and "private@example.test" not in caplog.text


def test_real_submission_pipeline_marks_d365_failure_and_keeps_private_values_out(caplog, tmp_path):
    caplog.set_level(logging.INFO, logger="app.workflow")
    settings = Settings(_env_file=None, local_resume_dir=tmp_path / "resumes",
                        sqlite_database_path=tmp_path / "metadata.sqlite3", d365_enabled=True,
                        d365_base_url="https://example.operations.dynamics.com", d365_tenant_id="test",
                        d365_client_id="private-client", d365_client_secret="private-client-secret",
                        public_rate_limit=999, upload_rate_limit=999)
    job = DemoAdapter().jobs[0].model_copy(update={"deadline": ""})

    def remote(request):
        if request.url.path.endswith("getOpenRequirements"):
            return httpx.Response(200, json={"Requirements": [job.model_dump(mode="json")]})
        return httpx.Response(500, json={
            "Message": "UBJobApplicationTable.ApplicationId is missing or exceeds its existing field length (20).",
            "ExceptionType": "ErrorException", "ActivityId": "6ab0631d-428e-49f7-bd91-7102c05af6ae",
        })

    http = httpx.AsyncClient(transport=httpx.MockTransport(remote))
    authentication = Mock(acquire_token_for_client=Mock(return_value={"access_token": "private-bearer-token"}))
    adapter = SQLiteD365Service(settings, client=http, msal_app=authentication)
    application = create_app(settings)
    application.state.adapter = adapter
    application.state.coordinator = SubmissionCoordinator(settings, adapter, application.state.resumes)
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Private Applicant built accessible React projects.")
    data = document.tobytes()
    document.close()
    try:
        with TestClient(application) as client:
            csrf = client.get("/api/auth/me").json()["csrf_token"]
            csrf = client.post("/api/auth/demo", json={"role": "candidate"},
                               headers={"X-CSRF-Token": csrf}).json()["csrf_token"]
            caplog.clear()
            result = client.post("/api/applications", headers={"X-CSRF-Token": csrf, "Idempotency-Key": "private-key-001"},
                                 data={"requirement_id": job.requirement_id, "consent_accepted": "true", "consent_version": "v1",
                                       "candidate_name": "Private Applicant", "email": "private-contact@example.test"},
                                 files={"resume": ("PrivateApplicant.pdf", data, "application/pdf")})
            assert result.status_code == 502
            request_id = result.headers["x-request-id"]
            failure = next(event for event in events(caplog)
                           if event["stage"] == "d365.http" and event["outcome"] == "failed")
            assert failure["request_id"] == request_id and failure["status_code"] == 500
            assert failure["issue_code"] == "field_length_or_missing" and failure["field"] == "ApplicationId"
            assert failure["max_length"] == 20 and failure["activity_id"] == "6ab0631d-428e-49f7-bd91-7102c05af6ae"
            assert failure["correlation_id"] in result.json()["detail"]
            assert failure["application_id"].startswith("APP-")
            assert any(event["stage"] == "submission.d365_submit" and event["outcome"] == "failed"
                       and event["application_id"] == failure["application_id"] for event in events(caplog))
            assert not any(event["stage"] == "submission.evaluation_enqueue" for event in events(caplog))
            retained = asyncio.run(adapter.metadata.get_application(failure["application_id"]))
            assert retained["stage"] == "ready"
    finally:
        asyncio.run(http.aclose())
    for private in ("Private Applicant", "private-contact@example.test", "PrivateApplicant.pdf",
                    "private-client-secret", "private-bearer-token", "private-key-001", csrf):
        assert private not in caplog.text


def test_uvicorn_access_and_exception_filters_remove_values_and_keep_code_locations():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1", "GET", "/auth/linkedin/callback?code=private-code&state=private-state", "1.1", 401), None)
    SafeAccessLogs().filter(record)
    assert "/auth/linkedin/callback" in record.getMessage() and "private" not in record.getMessage()
    try:
        raise ValueError("private-provider-token")
    except ValueError:
        record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1, "ASGI failure",
                                   (), sys.exc_info())
    SafeExceptionLogs().filter(record)
    rendered = logging.Formatter("%(message)s").format(record)
    assert "ValueError" in rendered and "test_observability.py:" in rendered
    assert "private-provider-token" not in rendered and record.exc_info is None


def test_explicit_sdk_child_debug_and_warning_are_safe_at_terminal():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(SafeSDKLogs())
    for level in (logging.DEBUG, logging.WARNING):
        handler.handle(logging.LogRecord("azure.core.generated.serialization", level, __file__, 1,
                                        "response contains %s", ("private-profile@example.test",), None))
    assert output.getvalue().count("sdk_warning") == 1
    assert "private" not in output.getvalue()


def test_invalid_startup_settings_do_not_echo_environment_inputs(tmp_path):
    environment = {**os.environ, "APP_ENV": "production", "DEMO_MODE": "true",
                   "LINKEDIN_CLIENT_SECRET": "private-linkedin-token", "AZURE_OPENAI_API_KEY": "private-openai-key"}
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-c", "from app.config import get_settings; get_settings()"],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    text = result.stdout + result.stderr
    assert "stage=configuration.validate" in text and "production_configuration" in text
    assert "ConfigurationError" in text
    assert "private-linkedin-token" not in text and "private-openai-key" not in text


def test_invalid_worker_redis_url_does_not_echo_credential_or_invalid_port(tmp_path):
    environment = {**os.environ, "APP_ENV": "development", "DEMO_MODE": "true",
                   "REDIS_URL": "redis://default:private-password@localhost:private-invalid-port"}
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-c", "from app.worker import WorkerSettings"],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    text = result.stdout + result.stderr
    assert "stage=worker.redis.configuration" in text and "ConfigurationError" in text
    assert "private-password" not in text and "private-invalid-port" not in text


def test_log_metadata_is_allowlisted_bounded_and_single_line(caplog):
    caplog.set_level(logging.INFO, logger="app.workflow")
    log_event("test.metadata", "completed", payload={"email": "private@example.test"},
              exception="private-error", provider_message="private@example.test", hint="https://secret.test/key",
              request_id="not-a-uuid", company="USMF\nsecret", response_bytes=10 ** 1000,
              count=2, configured=True)
    assert events(caplog) == [{"stage": "test.metadata", "outcome": "completed", "count": 2, "configured": True}]
    assert "private" not in caplog.text and "secret" not in caplog.text


def test_debug_contract_shape_shows_field_length_without_value(caplog):
    caplog.set_level(logging.DEBUG, logger="app.workflow")
    log_request_shape("submit_application", {"_request": {"ApplicationId": "APP-private", "Email": "private@example.test",
                                                          "Unexpected": "private-token"}})
    assert [(event["field"], event["value_length"]) for event in events(caplog)] == [("ApplicationId", 11), ("Email", 20)]
    assert all(event["value_type"] == "str" for event in events(caplog))
    assert "private" not in caplog.text and "Unexpected" not in caplog.text


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_application_log_level_configuration_preserves_safe_default(level):
    assert Settings(_env_file=None, log_level=level).log_level == level
