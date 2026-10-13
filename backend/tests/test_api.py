import asyncio
from unittest.mock import AsyncMock

import httpx
import pymupdf
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def pdf_bytes():
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Fictional applicant: built React accessible dashboard with keyboard navigation.")
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def client(tmp_path):
    app = create_app(
        Settings(_env_file=None, local_resume_dir=tmp_path / "resumes", public_rate_limit=999, upload_rate_limit=999)
    )
    with TestClient(app, raise_server_exceptions=False) as session:
        yield session


def login(client, role="candidate"):
    auth = client.get("/api/auth/me").json()
    result = client.post("/api/auth/demo", json={"role": role}, headers={"X-CSRF-Token": auth["csrf_token"]})
    assert result.status_code == 200, result.text
    return result.json()["csrf_token"]


def login_linkedin(client, monkeypatch, **profile_fields):
    profile = {
        "sub": "linkedin-user-001",
        "issuer": "https://www.linkedin.com/oauth",
        "role": "candidate",
        "name": "",
        "email": "",
        **profile_fields,
    }

    async def callback(request, provider):
        assert provider == "linkedin"
        request.session.clear()
        request.session.update(user=profile, csrf_token="test-linkedin-csrf")
        request.state.rotate_session = True

    monkeypatch.setattr(client.app.state.oidc, "callback", callback)
    result = client.get("/auth/linkedin/callback", follow_redirects=False)
    assert result.status_code == 303, result.text
    auth = client.get("/api/auth/me").json()
    assert auth["user"] == profile
    return auth["csrf_token"]


def submit(client, csrf, data, key="test-application-001", **fields):
    payload = {"requirement_id": "REQ-2026-001", "consent_accepted": "true", "consent_version": "v1", **fields}
    return client.post(
        "/api/applications",
        data=payload,
        files={"resume": ("resume.pdf", data, "application/pdf")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
    )


def test_public_jobs_search_filters_and_private_guards(client):
    assert len(client.get("/api/jobs").json()) == 6
    assert all("React" in j["required_skills"] for j in client.get("/api/jobs?search=React").json())
    assert len(client.get("/api/jobs?department=Design").json()) == 1
    assert client.get("/api/jobs/no-such-job").status_code == 404
    assert client.get("/api/me/applications").status_code == 401
    assert client.get("/api/hr/jobs").status_code == 401
    login(client)
    assert client.get("/api/hr/jobs").status_code == 403


def test_configured_consent_version_is_available_and_required(tmp_path, pdf_bytes):
    app = create_app(Settings(_env_file=None, local_resume_dir=tmp_path / "resumes", consent_version="v2"))
    with TestClient(app) as session:
        notice = session.get("/api/auth/me").json()
        assert notice["consent_version"] == "v2"
        authenticated = session.post(
            "/api/auth/demo", json={"role": "candidate"}, headers={"X-CSRF-Token": notice["csrf_token"]}
        ).json()
        assert authenticated["consent_version"] == "v2"
        csrf = authenticated["csrf_token"]
        assert submit(session, csrf, pdf_bytes, consent_version="v1").status_code == 422
        assert submit(session, csrf, pdf_bytes, consent_version=authenticated["consent_version"]).status_code == 200


def test_csrf_origin_and_login_cookie_rotation(client):
    initial = client.get("/api/auth/me")
    old_cookie = client.cookies.get("talentmatch_session")
    assert "HttpOnly" in initial.headers["set-cookie"]
    assert client.post("/api/auth/demo", json={"role": "candidate"}).status_code == 403
    token = initial.json()["csrf_token"]
    assert (
        client.post(
            "/api/auth/demo",
            json={"role": "candidate"},
            headers={"X-CSRF-Token": token, "Origin": "https://untrusted.test"},
        ).status_code
        == 403
    )
    csrf = login(client)
    assert old_cookie != client.cookies.get("talentmatch_session")
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/auth/me").json()["user"] is None


def test_application_real_upload_idempotency_ownership_and_hr_download(client, pdf_bytes):
    csrf = login(client)
    first = submit(client, csrf, pdf_bytes)
    assert first.status_code == 200, first.text
    application_id = first.json()["application_id"]
    assert submit(client, csrf, pdf_bytes).json()["application_id"] == application_id
    assert submit(client, csrf, pdf_bytes + b"x").status_code == 409
    own = client.get(f"/api/applications/{application_id}").json()
    assert "evaluation" not in own and "owner_sub" not in own and "resume_ref" not in own
    history = client.get("/api/me/applications").json()
    assert len(history) == 1 and history[0]["application_id"] == application_id
    assert "evaluation" not in history[0]
    assert client.get("/api/applications/DEMO-APP-001").status_code == 404
    assert client.get(f"/api/hr/applications/{application_id}/resume").status_code == 403
    login(client, "hr")
    ranked = client.get("/api/hr/jobs/REQ-2026-001/candidates").json()
    scores = [c["evaluation"]["score"] for c in ranked["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert ranked["returned_count"] == len(ranked["candidates"])
    assert all("owner_sub" not in c and "resume_ref" not in c for c in ranked["candidates"])
    detail = client.get(f"/api/hr/jobs/REQ-2026-001/candidates/{application_id}").json()
    assert detail["demo_fixture"] and "FICTIONAL" in detail["evaluation"]["score_justification"]
    downloaded = client.get(f"/api/hr/applications/{application_id}/resume")
    assert downloaded.status_code == 200 and downloaded.content == pdf_bytes
    assert downloaded.headers["content-type"] == "application/pdf"
    assert client.get(f"/api/hr/jobs/REQ-2026-002/candidates/{application_id}").status_code == 404


def test_linkedin_without_optional_profile_can_apply_with_contact_and_keeps_identity(client, pdf_bytes, monkeypatch):
    csrf = login_linkedin(client, monkeypatch)
    adapter = client.app.state.adapter
    submitted = AsyncMock(wraps=adapter.submit_application)
    monkeypatch.setattr(adapter, "submit_application", submitted)
    result = submit(
        client,
        csrf,
        pdf_bytes,
        candidate_name="  Sritharoon Kumar  ",
        email="  sritharoon+jobs@example.test  ",
        role="hr",
        owner_sub="different-user",
        owner_issuer="different-issuer",
    )
    assert result.status_code == 200, result.text
    application_id = result.json()["application_id"]
    submitted.assert_awaited_once()
    payload = submitted.call_args.args[0]
    assert payload["candidate_name"] == "Sritharoon Kumar"
    assert payload["email"] == "sritharoon+jobs@example.test"
    assert payload["owner_sub"] == "linkedin-user-001"
    assert payload["owner_issuer"] == "https://www.linkedin.com/oauth"
    own = client.get(f"/api/applications/{application_id}")
    assert own.status_code == 200
    assert own.json()["candidate_name"] == "Sritharoon Kumar"
    assert own.json()["email"] == "sritharoon+jobs@example.test"
    assert [record["application_id"] for record in client.get("/api/me/applications").json()] == [application_id]
    session_user = client.get("/api/auth/me").json()["user"]
    assert session_user["name"] == session_user["email"] == ""
    assert session_user["role"] == "candidate"
    assert client.get("/api/hr/jobs").status_code == 403
    login_linkedin(
        client,
        monkeypatch,
        sub="another-linkedin-user",
        name="Sritharoon Kumar",
        email="sritharoon+jobs@example.test",
    )
    assert client.get("/api/me/applications").json() == []
    assert client.get(f"/api/applications/{application_id}").status_code == 404


@pytest.mark.parametrize(
    "contact",
    [
        {},
        {"candidate_name": "Applicant"},
        {"email": "applicant@example.test"},
        {"candidate_name": "", "email": "applicant@example.test"},
        {"candidate_name": "  ", "email": "applicant@example.test"},
        {"candidate_name": "12345", "email": "applicant@example.test"},
        {"candidate_name": "Applicant\nInjected", "email": "applicant@example.test"},
        {"candidate_name": "A" * 201, "email": "applicant@example.test"},
        {"candidate_name": "Applicant", "email": ""},
        {"candidate_name": "Applicant", "email": "  "},
        {"candidate_name": "Applicant", "email": "not-an-email"},
        {"candidate_name": "Applicant", "email": "applicant@example"},
        {"candidate_name": "Applicant", "email": "applicant@example..test"},
        {"candidate_name": "Applicant", "email": "applicant@-example.test"},
        {"candidate_name": "Applicant", "email": "applicant..name@example.test"},
        {"candidate_name": "Applicant", "email": "applicant@example.test\r\nInjected"},
        {"candidate_name": "Applicant", "email": "a" * 310 + "@example.test"},
    ],
)
def test_required_contact_rejected_before_resume_storage_or_application_submission(client, pdf_bytes, monkeypatch, contact):
    csrf = login_linkedin(client, monkeypatch)
    stored = AsyncMock(wraps=client.app.state.resumes.store)
    submitted = AsyncMock(wraps=client.app.state.adapter.submit_application)
    monkeypatch.setattr(client.app.state.resumes, "store", stored)
    monkeypatch.setattr(client.app.state.adapter, "submit_application", submitted)
    response = submit(client, csrf, pdf_bytes, **contact)
    assert response.status_code == 422, response.text
    stored.assert_not_awaited()
    submitted.assert_not_awaited()
    assert not list(client.app.state.settings.local_resume_dir.glob("*"))


@pytest.mark.parametrize("field", ["candidate_name", "email"])
def test_explicit_blank_contact_does_not_fall_back_to_authenticated_profile(client, pdf_bytes, field):
    csrf = login(client)
    assert submit(client, csrf, pdf_bytes, **{field: ""}).status_code == 422


def test_effective_contact_is_trimmed_and_part_of_application_idempotency(client, pdf_bytes, monkeypatch):
    csrf = login_linkedin(client, monkeypatch)
    stored = AsyncMock(wraps=client.app.state.resumes.store)
    submitted = AsyncMock(wraps=client.app.state.adapter.submit_application)
    monkeypatch.setattr(client.app.state.resumes, "store", stored)
    monkeypatch.setattr(client.app.state.adapter, "submit_application", submitted)
    contact = {"candidate_name": "Applicant", "email": "applicant@example.test"}
    first = submit(client, csrf, pdf_bytes, **contact)
    assert first.status_code == 200, first.text
    again = submit(client, csrf, pdf_bytes, candidate_name="  Applicant ", email=" applicant@example.test ")
    assert again.status_code == 200 and again.json()["application_id"] == first.json()["application_id"]
    assert submit(client, csrf, pdf_bytes, **{**contact, "candidate_name": "Changed Applicant"}).status_code == 409
    assert submit(client, csrf, pdf_bytes, **{**contact, "email": "changed@example.test"}).status_code == 409
    stored.assert_awaited_once()
    submitted.assert_awaited_once()


def test_omitted_contact_falls_back_to_existing_profile_with_same_effective_idempotency(client, pdf_bytes):
    csrf = login(client)
    first = submit(client, csrf, pdf_bytes)
    assert first.status_code == 200, first.text
    user = client.get("/api/auth/me").json()["user"]
    again = submit(client, csrf, pdf_bytes, candidate_name=user["name"], email=user["email"])
    assert again.status_code == 200 and again.json()["application_id"] == first.json()["application_id"]


def test_upload_validation_consent_closed_job_and_body_cap(client, pdf_bytes):
    csrf = login(client)
    assert submit(client, csrf, b"not-a-pdf").status_code == 422
    assert submit(client, csrf, pdf_bytes, consent_accepted="false").status_code == 422
    assert submit(client, csrf, pdf_bytes, consent_version="expired").status_code == 422
    assert submit(client, csrf, pdf_bytes, phone="<script>").status_code == 422
    assert submit(client, csrf, pdf_bytes, linkedin_url="https://linkedin.com.evil.test/in/x").status_code == 422
    client.app.state.adapter.jobs[0].status = "Closed"
    assert submit(client, csrf, pdf_bytes).status_code == 404
    oversized = b"x" * (12 * 1024 * 1024)
    result = client.post("/api/applications", content=oversized, headers={"Content-Type": "application/octet-stream"})
    assert result.status_code == 413


def test_demo_forbidden_in_production_and_configured_auth_missing(client):
    with pytest.raises(ValueError, match="DEMO_MODE"):
        Settings(_env_file=None, app_env="production")
    assert client.get("/auth/linkedin/login", follow_redirects=False).status_code == 503
    assert client.get("/auth/hr/login", follow_redirects=False).status_code == 503


async def test_logout_cannot_be_reversed_by_late_authenticated_get(tmp_path):
    app = create_app(Settings(_env_file=None, local_resume_dir=tmp_path))
    started, release = asyncio.Event(), asyncio.Event()

    @app.get("/review-wait")
    async def delayed(request: Request):
        loaded_user = request.session.get("user")
        started.set()
        await release.wait()
        return {"loaded_user": loaded_user}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as session:
        auth = (await session.get("/api/auth/me")).json()
        auth = (
            await session.post(
                "/api/auth/demo", json={"role": "candidate"}, headers={"X-CSRF-Token": auth["csrf_token"]}
            )
        ).json()
        old_sid = session.cookies.get("talentmatch_session")
        waiting = asyncio.create_task(session.get("/review-wait"))
        await started.wait()
        assert (await session.post("/api/auth/logout", headers={"X-CSRF-Token": auth["csrf_token"]})).status_code == 200
        release.set()
        late = await waiting
        assert "set-cookie" not in late.headers
        assert (await session.get("/api/auth/me")).json()["user"] is None
        session.cookies.clear()
        session.cookies.set("talentmatch_session", old_sid)
        assert (await session.get("/api/auth/me")).json()["user"] is None
