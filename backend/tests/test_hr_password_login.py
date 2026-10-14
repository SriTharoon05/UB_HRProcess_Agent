"""HR environment credentials must establish a protected server-side session."""

import logging
import os
import uuid

import pytest
from arq.connections import RedisSettings, create_pool
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


USERNAME = "fixture@staff"
PASSWORD = "test-only-password"


@pytest.fixture
def client(tmp_path):
    application = create_app(Settings(_env_file=None, hr_username=USERNAME, hr_password=PASSWORD,
                                      local_resume_dir=tmp_path, public_rate_limit=999, hr_login_rate_limit=99))
    with TestClient(application) as session:
        yield session


def csrf(client):
    return client.get("/api/auth/me").json()["csrf_token"]


def sign_in(client, token, username=USERNAME, password=PASSWORD, **extra):
    return client.post("/api/auth/hr", json={"username": username, "password": password, **extra},
                       headers={"X-CSRF-Token": token})


def test_success_rotates_session_and_csrf_and_authorizes_hr_only(client, caplog):
    caplog.set_level(logging.DEBUG, logger="app.workflow")
    token = csrf(client)
    old_cookie = client.cookies.get("talentmatch_session")
    assert client.get("/api/hr/jobs").status_code == 401
    result = sign_in(client, token)
    assert result.status_code == 200
    assert result.json()["user"]["role"] == "hr"
    assert result.json()["user"]["email"] == USERNAME
    assert result.json()["csrf_token"] != token
    assert client.cookies.get("talentmatch_session") != old_cookie
    assert "HttpOnly" in result.headers["set-cookie"]
    assert PASSWORD not in result.text and "password" not in result.json()["user"]
    assert client.get("/api/hr/jobs").status_code == 200
    assert client.get("/api/me/applications").status_code == 403
    assert client.get("/api/auth/me").json()["user"]["role"] == "hr"
    with TestClient(client.app) as replay:
        replay.cookies.set("talentmatch_session", old_cookie)
        assert replay.get("/api/hr/jobs").status_code == 401
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": result.json()["csrf_token"]}).status_code == 200
    assert client.get("/api/hr/jobs").status_code == 401
    assert USERNAME not in caplog.text and PASSWORD not in caplog.text
    assert "stage=auth.hr.password outcome=validated" in caplog.text


@pytest.mark.parametrize("username,password", [
    ("wrong@staff", PASSWORD), (USERNAME, "wrong-test-password"), (USERNAME.upper(), PASSWORD),
    (USERNAME, PASSWORD.upper()), (" " + USERNAME, PASSWORD),
])
def test_wrong_credentials_are_generic_and_do_not_grant_access(client, username, password, caplog):
    caplog.set_level(logging.DEBUG, logger="app.workflow")
    result = sign_in(client, csrf(client), username, password)
    assert result.status_code == 401 and result.json() == {"detail": "Invalid username or password"}
    assert client.get("/api/hr/jobs").status_code == 401
    assert client.get("/api/auth/me").json()["user"] is None
    assert username not in caplog.text and password not in caplog.text


def test_hr_login_requires_csrf_and_allowed_origin(client):
    token = csrf(client)
    body = {"username": USERNAME, "password": PASSWORD}
    assert client.post("/api/auth/hr", json=body).status_code == 403
    assert client.post("/api/auth/hr", json=body,
                       headers={"X-CSRF-Token": token, "Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/hr/jobs").status_code == 401


@pytest.mark.parametrize("fields", [{"hr_username": "", "hr_password": PASSWORD},
                                    {"hr_username": USERNAME, "hr_password": ""}])
def test_no_builtin_account_when_configuration_missing(fields, tmp_path):
    application = create_app(Settings(_env_file=None, local_resume_dir=tmp_path, **fields))
    with TestClient(application) as session:
        result = sign_in(session, csrf(session))
        assert result.status_code == 503 and "HR_USERNAME and HR_PASSWORD" in result.json()["detail"]
        assert session.get("/api/hr/jobs").status_code == 401


def test_login_attempts_have_separate_rate_limit(tmp_path):
    application = create_app(Settings(_env_file=None, local_resume_dir=tmp_path, hr_username=USERNAME,
                                      hr_password=PASSWORD, hr_login_rate_limit=2, public_rate_limit=999))
    with TestClient(application) as session:
        token = csrf(session)
        assert sign_in(session, token, password="wrong-test-password").status_code == 401
        assert sign_in(session, token, password="wrong-test-password").status_code == 401
        assert sign_in(session, token).status_code == 429
        assert session.get("/api/jobs").status_code == 200
        assert session.get("/api/hr/jobs").status_code == 401


def test_body_cannot_choose_identity_or_role_and_password_is_hidden_in_settings(client):
    assert sign_in(client, csrf(client), role="hr", issuer="forged").status_code == 422
    assert USERNAME not in repr(client.app.state.settings) and PASSWORD not in repr(client.app.state.settings)


async def test_connected_production_hr_login_uses_secure_redis_session_without_entra(tmp_path):
    redis_url = os.environ.get("REDIS_TEST_URL")
    if not redis_url:
        pytest.skip("Set REDIS_TEST_URL for isolated connected HR session verification")
    prefix = "hr-password-test-" + uuid.uuid4().hex
    settings = Settings(_env_file=None, app_env="production", demo_mode=False, redis_url=redis_url,
                        redis_prefix=prefix, sqlite_database_path=tmp_path / "metadata.sqlite3",
                        frontend_url="https://portal.example", backend_url="https://portal.example",
                        cors_origins=["https://portal.example"], hr_username=USERNAME, hr_password=PASSWORD)
    application = create_app(settings)
    redis = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        with TestClient(application, base_url="https://portal.example") as session:
            token = csrf(session)
            result = sign_in(session, token)
            assert result.status_code == 200 and result.json()["demo_mode"] is False
            assert "Secure" in result.headers["set-cookie"]
            assert session.get("/api/auth/me").json()["user"]["role"] == "hr"
            assert session.get("/api/me/applications").status_code == 403
            cookie = session.cookies.get("talentmatch_session")
        stored = await redis.get(f"{prefix}:session:{cookie}")
        assert stored and PASSWORD.encode() not in stored
    finally:
        keys = [key async for key in redis.scan_iter(match=prefix + ":*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()
