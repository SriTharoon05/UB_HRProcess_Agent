import asyncio

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
