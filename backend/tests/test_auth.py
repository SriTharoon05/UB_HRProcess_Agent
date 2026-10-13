import base64
import hashlib
import logging
import time
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi import HTTPException
from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.requests import Request

from app.auth import OIDC, oauth_return_path
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
    ],
)
async def test_linkedin_rejects_missing_or_subject_mismatched_profile(profile):
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value = profile
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 401
    assert "user" not in req.session


@pytest.mark.parametrize(
    "profile, expected_name, expected_email",
    [
        ({"sub": "user-1"}, "", ""),
        ({"sub": "user-1", "name": "Fictional Tester"}, "Fictional Tester", ""),
        ({"sub": "user-1", "email": "test@example.test"}, "", "test@example.test"),
        (
            {"sub": "user-1", "name": "Fictional Tester", "email": "test@example.test", "email_verified": False},
            "Fictional Tester",
            "test@example.test",
        ),
        (
            {"sub": "user-1", "name": "Fictional Tester", "email": "test@example.test"},
            "Fictional Tester",
            "test@example.test",
        ),
        ({"sub": "user-1", "name": None, "email": None}, "", ""),
        ({"sub": "user-1", "name": 123, "email": {"invalid": "email"}}, "", ""),
        (
            {"sub": "user-1", "given_name": " Fictional ", "family_name": " Tester "},
            "Fictional Tester",
            "",
        ),
        ({"sub": "user-1", "given_name": "Fictional", "family_name": ["Invalid"]}, "Fictional", ""),
        (
            {"sub": "user-1", "name": " Fictional Tester ", "email": " test@example.test "},
            "Fictional Tester",
            "test@example.test",
        ),
    ],
)
async def test_linkedin_profile_contact_fields_are_optional_and_do_not_define_identity(
    profile, expected_name, expected_email
):
    oidc, client, req = await configured_callback(omitted=("nonce", "name", "email", "email_verified"))
    client.userinfo.return_value = profile
    user = await oidc.callback(req, "linkedin")
    assert user.name == expected_name and user.email == expected_email
    assert user.sub == "user-1" and user.issuer == oidc.settings.linkedin_issuer
    assert user.role == "candidate" and req.session["user"]["role"] == "candidate"
    assert req.state.rotate_session


@pytest.mark.parametrize(
    "profile",
    [
        {"sub": "user-1"},
        {"sub": "user-1", "name": None, "email": None, "email_verified": None},
    ],
)
async def test_linkedin_omitted_profile_contacts_preserve_validated_token_contacts(profile):
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value = profile
    user = await oidc.callback(req, "linkedin")
    assert user.name == "Fictional Tester" and user.email == "test@example.test"
    assert user.sub == "user-1" and user.issuer == oidc.settings.linkedin_issuer
    assert user.role == "candidate"


async def test_linkedin_supplied_malformed_profile_contacts_are_not_used_as_text():
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value = {"sub": "user-1", "name": ["Not a name"], "email": {"not": "an email"}}
    user = await oidc.callback(req, "linkedin")
    assert user.name == "" and user.email == ""
    assert user.sub == "user-1" and user.role == "candidate"


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


@pytest.mark.parametrize("claim", ["name", "email"])
async def test_entra_still_requires_profile_contact_fields(claim):
    oidc, client, req = await configured_callback(provider="hr", omitted=(claim,))
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "hr")
    assert error.value.status_code == 401
    assert error.value.detail == "Identity is missing required profile information"
    assert "user" not in req.session
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


@pytest.mark.parametrize(
    "provider, destination",
    [
        ("linkedin", "/"),
        ("linkedin", "/jobs?search=React%20Developer&department=Engineering#open-roles"),
        ("linkedin", "/jobs/REQ-2026-001"),
        ("linkedin", "/jobs/REQ%20A/apply"),
        ("linkedin", "/candidate/applications"),
        ("linkedin", "/candidate/applications/APP-001"),
        ("hr", "/hr"),
        ("hr", "/hr/jobs"),
        ("hr", "/hr/jobs/REQ-001/candidates?limit=10"),
        ("hr", "/hr/jobs/REQ-001/candidates/APP-001"),
    ],
)
def test_oauth_return_allows_only_portal_routes_for_provider(provider, destination):
    assert oauth_return_path(destination, provider) == destination


@pytest.mark.parametrize(
    "destination",
    [
        "https://evil.test/jobs/REQ-001/apply",
        "//evil.test/jobs/REQ-001/apply",
        "/%2f%2fevil.test",
        "/jobs/REQ-001/../apply",
        "/jobs/../hr",
        "/jobs/%2e%2e/apply",
        "/jobs/%252e%252e/apply",
        "/jobs/REQ%2fOTHER/apply",
        "/jobs/REQ%252fOTHER/apply",
        "/jobs//apply",
        "/jobs/REQ-001/apply/",
        "\\\\evil.test\\jobs\\REQ-001\\apply",
        "/jobs/REQ-001\\apply",
        "/jobs/REQ-001%5capply",
        "/jobs/REQ-001/apply?search=%0d%0aLocation%3Aevil",
        "/jobs/REQ-001/apply#%250aInjected",
        "/jobs/REQ-001/apply\x7f",
        "/jobs/REQ-001/apply\n",
        "jobs/REQ-001/apply",
        "",
        "/auth/linkedin/callback",
        "/login",
        "/hr",
        "/hr/jobs/REQ-001/candidates",
        "/jobs/" + "x" * 2048,
    ],
)
def test_linkedin_return_rejects_external_ambiguous_or_wrong_role_destinations(destination):
    with pytest.raises(HTTPException) as error:
        oauth_return_path(destination, "linkedin")
    assert error.value.status_code == 400


@pytest.mark.parametrize("destination", ["/", "/jobs/REQ-001/apply", "/candidate/applications", "/auth/hr/login"])
def test_hr_return_rejects_candidate_and_auth_destinations(destination):
    with pytest.raises(HTTPException) as error:
        oauth_return_path(destination, "hr")
    assert error.value.status_code == 400


async def test_login_binds_each_return_destination_to_its_own_server_side_oauth_state():
    oidc, client, req = await configured_callback()
    client.load_server_metadata.return_value["authorization_endpoint"] = "https://www.linkedin.com/oauth/v2/authorization"
    req.session.clear()
    previous_state = None
    for destination in ("/jobs/REQ-001/apply", "/jobs/REQ-002/apply"):
        req = Request({**req.scope, "query_string": urlencode({"return_to": destination}).encode()})
        response = await oidc.login(req, "linkedin")
        params = parse_qs(urlsplit(response.headers["location"]).query)
        state = params["state"][0]
        state_data = await client.framework.get_state_data(req.session, state)
        assert state_data["return_to"] == destination
        assert state_data["nonce"] == params["nonce"][0]
        assert state_data["redirect_uri"] == oidc.settings.linkedin_redirect_uri
        assert "return_to" not in params
        if previous_state:
            assert state != previous_state
            # Authlib invalidates previous attempts instead of sharing the
            # latest destination with an older callback.
            assert await client.framework.get_state_data(req.session, previous_state) is None
        previous_state = state


async def test_login_rejects_invalid_return_before_authorization_request():
    oidc, client, req = await configured_callback()
    client.create_authorization_url = AsyncMock()
    req.scope["query_string"] = urlencode({"return_to": "https://evil.test"}).encode()
    with pytest.raises(HTTPException) as error:
        await oidc.login(req, "linkedin")
    assert error.value.status_code == 400
    client.create_authorization_url.assert_not_awaited()


async def test_callback_uses_stored_job_destination_and_ignores_callback_override():
    oidc, client, req = await configured_callback()
    state_data = await client.framework.get_state_data(req.session, "expected-state")
    await client.framework.set_state_data(
        req.session, "expected-state", {**state_data, "return_to": "/jobs/REQ-001/apply?source=jobs#contact"}
    )
    req.scope["query_string"] = urlencode(
        {"state": "expected-state", "code": "code", "return_to": "https://evil.test"}
    ).encode()
    user = await oidc.callback(req, "linkedin")
    assert user.role == "candidate"
    assert req.state.oauth_return_to == "/jobs/REQ-001/apply?source=jobs#contact"
    assert all("_state_" not in key for key in req.session)


async def test_callback_revalidates_stored_destination_before_token_exchange():
    oidc, client, req = await configured_callback()
    state_data = await client.framework.get_state_data(req.session, "expected-state")
    await client.framework.set_state_data(req.session, "expected-state", {**state_data, "return_to": "/hr"})
    with pytest.raises(HTTPException) as error:
        await oidc.callback(req, "linkedin")
    assert error.value.status_code == 400
    client.fetch_access_token.assert_not_awaited()
    assert "user" not in req.session
    assert not hasattr(req.state, "oauth_return_to")


@pytest.mark.parametrize("provider, destination", [("linkedin", "/candidate/applications"), ("hr", "/hr")])
async def test_callback_without_return_destination_preserves_existing_defaults(provider, destination):
    oidc, _, req = await configured_callback(provider=provider)
    await oidc.callback(req, provider)
    assert req.state.oauth_return_to == destination


async def test_linkedin_exposes_only_sanitized_standard_public_profile_fields():
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value.update(
        given_name=" Fictional ", family_name=" Tester ",
        picture="https://media.licdn.com/dms/image/test-avatar", locale={"language": "en", "country": "US"},
        access_token="private-access-token", refresh_token="private-refresh-token", id_token="private-id-token",
        phone_number="private-phone", address={"private-address": "secret"}, arbitrary="private-provider-field",
    )
    user = await oidc.callback(req, "linkedin")
    assert user.linkedin_profile.model_dump(exclude_none=True) == {
        "sub": "user-1", "issuer": oidc.settings.linkedin_issuer,
        "name": "Fictional Tester", "given_name": "Fictional", "family_name": "Tester",
        "email": "test@example.test", "email_verified": True,
        "picture": "https://media.licdn.com/dms/image/test-avatar", "locale": "en-US",
    }
    assert "private-" not in str(req.session)
    assert "token" not in str(req.session["user"])


@pytest.mark.parametrize(
    "email",
    ["urn:li:member:1503054821", "invalid", "x@example", "a..b@example.test", "a@-example.test", "a@example.test\nInjected"],
)
async def test_linkedin_does_not_use_member_ids_or_invalid_contacts_as_email(email):
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value.update(email=email, email_verified=True)
    user = await oidc.callback(req, "linkedin")
    assert user.email == "" and user.linkedin_profile.email is None
    assert user.linkedin_profile.email_verified is None


@pytest.mark.parametrize("verified", [None, "true", 1])
async def test_changed_profile_email_does_not_inherit_verification_from_another_address(verified):
    oidc, client, req = await configured_callback(omitted=("nonce",))
    client.userinfo.return_value = {"sub": "user-1", "email": "different@example.test", "email_verified": verified}
    user = await oidc.callback(req, "linkedin")
    assert user.email == "different@example.test"
    assert user.linkedin_profile.email_verified is None


@pytest.mark.parametrize(
    "picture",
    [
        "javascript:alert(1)", "http://media.licdn.com/avatar", "https://127.0.0.1/private", "https://evil.test/avatar",
        "https://media.licdn.com.evil.test/avatar", "https://user:password@media.licdn.com/avatar",
        "https://media.licdn.com:444/avatar", "https://media.licdn.com/ava tar", "https://media.licdn.com/ava\\tar",
    ],
)
async def test_linkedin_unsafe_profile_picture_is_omitted(picture):
    oidc, client, req = await configured_callback()
    client.userinfo.return_value["picture"] = picture
    user = await oidc.callback(req, "linkedin")
    assert user.linkedin_profile.picture is None


@pytest.mark.parametrize(
    "locale, expected",
    [("en-US", "en-US"), ("en_US", "en-US"), ({"language": "ta", "country": "IN"}, "ta-IN"),
     ({"language": "en"}, "en"), ({"language": 123, "country": "US"}, None),
     ({"language": "en", "country": []}, None), ("<script>", None)],
)
async def test_linkedin_locale_supports_standard_string_and_provider_object(locale, expected):
    oidc, client, req = await configured_callback()
    client.userinfo.return_value["locale"] = locale
    user = await oidc.callback(req, "linkedin")
    assert user.linkedin_profile.locale == expected


async def test_hr_identity_has_no_linkedin_profile():
    oidc, _, req = await configured_callback(provider="hr")
    user = await oidc.callback(req, "hr")
    assert user.linkedin_profile is None
