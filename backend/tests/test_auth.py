import base64
import hashlib
import logging
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


async def configured_callback(provider="linkedin", omitted=(), invalid_signature=False, **changed):
    settings = Settings(
        _env_file=None,
        linkedin_client_id="test-client",
        linkedin_client_secret="test-secret",
        entra_tenant_id="tenant-1",
        entra_client_id="hr-client",
        entra_client_secret="hr-secret",
    )
    oidc = OIDC(settings)
    client = oidc.client(provider)
    key = RSAKey.generate_key(2048)
    key.ensure_kid()
    issuer = settings.linkedin_issuer if provider == "linkedin" else "https://login.microsoftonline.com/tenant-1/v2.0"
    claims = {
        "iss": issuer,
        "sub": "user-1",
        "aud": settings.linkedin_client_id if provider == "linkedin" else settings.entra_client_id,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "nonce": "expected-nonce",
        "name": "Fictional Tester",
        "email": "test@example.test",
        "email_verified": True,
        **({"tid": "tenant-1", "roles": ["HRRecruiter"]} if provider == "hr" else {}),
        **changed,
    }
    for claim in omitted:
        claims.pop(claim, None)
    signing_key = RSAKey.generate_key(2048) if invalid_signature else key
    token = jwt.encode({"alg": "RS256", "kid": key.kid}, claims, signing_key)
    client.fetch_access_token = AsyncMock(
        return_value={"id_token": token, "access_token": "test-access-token", "token_type": "Bearer"}
    )
    client.load_server_metadata = AsyncMock(
        return_value={"issuer": issuer, "id_token_signing_alg_values_supported": ["RS256"]}
    )
    client.fetch_jwk_set = AsyncMock(return_value={"keys": [key.as_dict(private=False)]})
    client.userinfo = AsyncMock(
        return_value={
            "sub": "user-1",
            "name": "Fictional Tester",
            "email": "test@example.test",
            "email_verified": True,
        }
    )
    req = request()
    req.scope["path"] = f"/auth/{provider}/callback"
    redirect_uri = settings.linkedin_redirect_uri if provider == "linkedin" else settings.entra_redirect_uri
    await client.framework.set_state_data(
        req.session, "expected-state", {"nonce": "expected-nonce", "redirect_uri": redirect_uri}
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
    assert client.fetch_access_token.await_count == 1
    assert client.userinfo.await_count == 1


async def test_linkedin_accepts_signed_token_without_nonce_and_uses_subject_bound_profile():
    oidc, client, req = await configured_callback(omitted=("nonce", "name", "email", "email_verified"))
    user = await oidc.callback(req, "linkedin")
    assert user.sub == "user-1"
    assert user.name == "Fictional Tester"
    assert user.email == "test@example.test"
    assert user.issuer == oidc.settings.linkedin_issuer
    assert user.role == "candidate"
    assert req.state.rotate_session
    assert "access_token" not in req.session and "id_token" not in req.session
    client.userinfo.assert_awaited_once_with(token=client.fetch_access_token.return_value)


async def test_linkedin_profile_cannot_overwrite_validated_identity_claims():
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value.update(
        iss="https://evil.test", aud="wrong-client", nonce="wrong-nonce", roles=["HRRecruiter"]
    )
    user = await oidc.callback(req, "linkedin")
    assert user.sub == "user-1"
    assert user.issuer == oidc.settings.linkedin_issuer and user.role == "candidate"


@pytest.mark.parametrize(
    "profile",
    [
        None,
        {},
        {"sub": "different-user", "name": "Other Person", "email": "other@example.test", "email_verified": True},
        {"sub": "", "name": "Fictional Tester", "email": "test@example.test", "email_verified": True},
        {"name": "Fictional Tester", "email": "test@example.test", "email_verified": True},
        {"sub": "user-1", "name": "Fictional Tester", "email": "test@example.test", "email_verified": False},
        {"sub": "user-1", "name": "Fictional Tester", "email": "test@example.test"},
        {"sub": "user-1", "email": "test@example.test", "email_verified": True},
        {"sub": "user-1", "name": "Fictional Tester", "email_verified": True},
    ],
)
async def test_linkedin_rejects_missing_unverified_or_subject_mismatched_profile(profile):
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value = profile
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session


async def test_linkedin_profile_failure_has_no_identity_token_fallback():
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.side_effect = RuntimeError("Synthetic userinfo transport failure")
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session


@pytest.mark.parametrize(
    "changed",
    [
        {"nonce": "wrong"},
        {"nonce": ""},
        {"nonce": None},
        {"iss": "https://evil.test"},
        {"aud": "wrong-client"},
        {"aud": "wrong-client", "azp": "test-client"},
        {"aud": ["wrong-client", "other-client"], "azp": "test-client"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
        {"nonce": "wrong", "nonce_supported": False},
        {"at_hash": "not-a-matching-hash"},
    ],
)
async def test_oidc_rejects_invalid_claims(changed):
    oidc, client, req = await configured_callback(**changed)
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session
    client.userinfo.assert_not_awaited()


async def test_linkedin_accepts_client_in_audience_list_with_valid_authorized_party():
    oidc, client, req = await configured_callback(aud=["test-client", "secondary-client"], azp="test-client")
    user = await oidc.callback(req, "linkedin")
    assert user.sub == "user-1" and user.role == "candidate"


async def test_linkedin_without_nonce_still_validates_access_token_hash():
    access_token_hash = (
        base64.urlsafe_b64encode(hashlib.sha256(b"test-access-token").digest()[:16]).rstrip(b"=").decode()
    )
    oidc, client, req = await configured_callback(omitted=("nonce",), at_hash=access_token_hash)
    user = await oidc.callback(req, "linkedin")
    assert user.sub == "user-1" and user.role == "candidate"


async def test_linkedin_without_nonce_rejects_wrong_access_token_hash():
    oidc, client, req = await configured_callback(omitted=("nonce",), at_hash="wrong-access-token-hash")
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session
    client.userinfo.assert_not_awaited()


@pytest.mark.parametrize(
    "oauth_error, claim, expected_error, expected_claim",
    [
        ("invalid_client", "nonce", "invalid_client", "nonce"),
        ("private-error-content", "private-claim-content", "unclassified", "-"),
        (["private-error-content"], {"private-claim-content": True}, "unclassified", "-"),
    ],
)
async def test_callback_diagnostics_exclude_exception_contents(
    caplog, oauth_error, claim, expected_error, expected_claim
):
    class UnsafeProviderError(Exception):
        pass

    oidc, client, req = await configured_callback()
    failure = UnsafeProviderError("code=private-code access_token=private-token client_secret=private-secret")
    failure.error = oauth_error
    failure.claim_name = claim
    client.fetch_access_token.side_effect = failure
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"), pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert error.value.detail == "Authentication callback could not be validated"
    assert f"type=UnsafeProviderError error={expected_error} claim={expected_claim}" in caplog.text
    assert "private-" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert "user" not in req.session


@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "sub"])
async def test_linkedin_rejects_missing_required_identity_claim(claim):
    oidc, client, req = await configured_callback(omitted=(claim,))
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session
    client.userinfo.assert_not_awaited()


async def test_linkedin_rejects_invalid_signature_before_profile_request():
    oidc, client, req = await configured_callback(invalid_signature=True)
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session
    client.userinfo.assert_not_awaited()


async def test_linkedin_requires_signed_identity_token():
    oidc, client, req = await configured_callback()
    client.fetch_access_token.return_value.pop("id_token")
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session
    client.userinfo.assert_not_awaited()


async def test_entra_still_requires_nonce_in_signed_identity_token():
    oidc, client, req = await configured_callback(provider="hr", omitted=("nonce",))
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "hr")
    assert error.value.status_code == 401
    assert "user" not in req.session
    client.userinfo.assert_not_awaited()


async def test_entra_accepts_valid_signed_identity_and_nonce_without_profile_fetch():
    oidc, client, req = await configured_callback(provider="hr")
    user = await oidc.callback(req, "hr")
    assert user.sub == "user-1" and user.role == "hr"
    assert req.state.rotate_session
    client.userinfo.assert_not_awaited()


async def test_oidc_rejects_unknown_state_before_token_exchange():
    oidc, client, req = await configured_callback()
    req.scope["query_string"] = b"code=code&state=forged"
    with pytest.raises(HTTPException):
        await oidc.callback(req, "linkedin")
    client.fetch_access_token.assert_not_called()
    client.userinfo.assert_not_awaited()


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
