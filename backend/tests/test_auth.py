import time
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.requests import Request

from app.auth import OIDC
from app.config import Settings


def request(state="expected-state"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/linkedin/callback",
            "query_string": f"code=code&state={state}".encode(),
            "headers": [],
            "session": {},
            "state": {},
        }
    )


async def configured_callback(**changed):
    settings = Settings(_env_file=None, linkedin_client_id="test-client", linkedin_client_secret="test-secret")
    oidc = OIDC(settings)
    client = oidc.client("linkedin")
    key = RSAKey.generate_key(2048)
    key.ensure_kid()
    claims = {
        "iss": settings.linkedin_issuer,
        "sub": "user-1",
        "aud": settings.linkedin_client_id,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "nonce": "expected-nonce",
        "name": "Fictional Tester",
        "email": "test@example.test",
        "email_verified": True,
        **changed,
    }
    token = jwt.encode({"alg": "RS256", "kid": key.kid}, claims, key)
    client.fetch_access_token = AsyncMock(
        return_value={"id_token": token, "access_token": "test-access-token", "token_type": "Bearer"}
    )
    client.load_server_metadata = AsyncMock(
        return_value={"issuer": settings.linkedin_issuer, "id_token_signing_alg_values_supported": ["RS256"]}
    )
    client.fetch_jwk_set = AsyncMock(return_value={"keys": [key.as_dict(private=False)]})
    req = request()
    await client.framework.set_state_data(
        req.session, "expected-state", {"nonce": "expected-nonce", "redirect_uri": settings.linkedin_redirect_uri}
    )
    return oidc, client, req


async def test_oidc_signed_token_state_nonce_issuer_audience_and_replay():
    oidc, client, req = await configured_callback()
    user = await oidc.callback(req, "linkedin")
    assert user.sub == "user-1" and user.role == "candidate"
    assert req.state.rotate_session and "access_token" not in req.session
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "changed",
    [
        {"nonce": "wrong"},
        {"iss": "https://evil.test"},
        {"aud": "wrong-client"},
        {"exp": 1},
        {"email_verified": False},
        {"nonce": "wrong", "nonce_supported": False},
    ],
)
async def test_oidc_rejects_invalid_claims(changed):
    oidc, client, req = await configured_callback(**changed)
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session


async def test_oidc_rejects_unknown_state_before_token_exchange():
    oidc, client, req = await configured_callback()
    req.scope["query_string"] = b"code=code&state=forged"
    with pytest.raises(HTTPException):
        await oidc.callback(req, "linkedin")
    client.fetch_access_token.assert_not_called()


def test_entra_role_tenant_and_issuer_checks():
    settings = Settings(_env_file=None, entra_tenant_id="tenant-1")
    oidc = OIDC(settings)
    claims = {
        "iss": "https://login.microsoftonline.com/tenant-1/v2.0",
        "tid": "tenant-1",
        "sub": "hr-1",
        "name": "Fictional HR",
        "preferred_username": "hr@example.test",
        "roles": ["HRRecruiter"],
    }
    assert oidc.identity(claims, "hr").role == "hr"
    for changes in [{"roles": []}, {"tid": "wrong"}, {"iss": "https://evil.test"}]:
        with pytest.raises(HTTPException):
            oidc.identity({**claims, **changes}, "hr")
