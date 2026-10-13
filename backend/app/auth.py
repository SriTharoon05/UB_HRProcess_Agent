import json
import logging
import re
import secrets
from http.cookies import SimpleCookie
from typing import Literal
from urllib.parse import unquote, urlsplit

from authlib.integrations.starlette_client import OAuth
from authlib.integrations.starlette_client.apps import StarletteOAuth2App
from authlib.oidc.core import CodeIDToken
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from starlette.responses import JSONResponse, RedirectResponse

from app.config import Settings
from app.errors import ConfigurationError
from app.models import User
from app.profile import linkedin_profile


def oauth_return_path(value: str | None, provider: str) -> str:
    """Only portal routes for the signing-in role can be OAuth destinations."""
    default = "/candidate/applications" if provider == "linkedin" else "/hr"
    if value is None:
        return default
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise HTTPException(400, "Invalid sign-in return destination")
    decoded = value
    for _ in range(6):
        if "\\" in decoded or not decoded.isprintable():
            raise HTTPException(400, "Invalid sign-in return destination")
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    else:
        raise HTTPException(400, "Invalid sign-in return destination")
    try:
        parts = urlsplit(value)
        decoded_path = unquote(parts.path)
        for _ in range(6):
            expanded = unquote(decoded_path)
            if expanded == decoded_path:
                break
            decoded_path = expanded
        if (
            parts.scheme
            or parts.netloc
            or not parts.path.startswith("/")
            or decoded_path.startswith("//")
            or "\\" in decoded_path
            or (any(part in {".", "..", ""} for part in decoded_path[1:].split("/")) and decoded_path != "/")
        ):
            raise ValueError("Unsafe relative path")
        identifier = r"[^/?#]+"
        pattern = (
            rf"/(?:jobs(?:/{identifier}(?:/apply)?)?|candidate/applications(?:/{identifier})?)?"
            if provider == "linkedin"
            else rf"/hr(?:/jobs(?:/{identifier}(?:/candidates(?:/{identifier})?)?)?|/applications/{identifier})?"
        )
        if not re.fullmatch(pattern, decoded_path):
            raise ValueError("Destination is outside this role's portal")
    except ValueError:
        raise HTTPException(400, "Invalid sign-in return destination") from None
    return value


class LinkedInCodeIDToken(CodeIDToken):
    """LinkedIn may omit nonce in its authorization-code ID tokens."""

    def validate_nonce(self):
        if "nonce" in self:
            super().validate_nonce()


class LinkedInOAuthApp(StarletteOAuth2App):
    async def parse_id_token(self, token, nonce, claims_options=None, claims_cls=None, leeway=120):
        def linkedin_claims(claims, header, options, params):
            # Authlib does not inject access_token when a custom claims class is
            # supplied. Preserve at_hash verification as well as all JWT checks.
            return LinkedInCodeIDToken(claims, header, options, {**params, "access_token": token.get("access_token")})

        return await super().parse_id_token(
            token, nonce, claims_options=claims_options, claims_cls=linkedin_claims, leeway=leeway
        )


class SessionStore:
    """Opaque random session identifiers. No identity or tokens go in cookies."""

    def __init__(self, settings: Settings, redis: Redis | None = None):
        self.settings = settings
        self.redis = redis
        self.memory: dict[str, dict] = {}

    def key(self, sid):
        return f"{self.settings.redis_prefix}:session:{sid}"

    async def get(self, sid):
        if self.redis:
            value = await self.redis.get(self.key(sid))
            return json.loads(value) if value else None
        import time

        item = self.memory.get(sid)
        if item and item["expires"] > time.time():
            return item["data"].copy()
        self.memory.pop(sid, None)
        return None

    async def put(self, sid, data, old_sid=None):
        """Atomically update/rotate only a still-valid original session."""
        if self.redis:
            if old_sid:
                script = """
                if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
                if KEYS[1] ~= KEYS[2] then redis.call('DEL', KEYS[1]) end
                redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
                return 1
                """
                return bool(
                    await self.redis.eval(
                        script, 2, self.key(old_sid), self.key(sid), json.dumps(data), self.settings.session_ttl_seconds
                    )
                )
            await self.redis.set(self.key(sid), json.dumps(data), ex=self.settings.session_ttl_seconds)
            return True
        else:
            import time

            if old_sid and (old_sid not in self.memory or self.memory[old_sid]["expires"] <= time.time()):
                return False
            if old_sid and old_sid != sid:
                self.memory.pop(old_sid, None)
            self.memory[sid] = {"data": data.copy(), "expires": time.time() + self.settings.session_ttl_seconds}
            return True

    async def delete(self, sid):
        if self.redis:
            await self.redis.delete(self.key(sid))
        else:
            self.memory.pop(sid, None)


class OpaqueSessionMiddleware:
    def __init__(self, app, settings: Settings, store: SessionStore):
        self.app, self.settings, self.store = app, settings, store

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cookie = SimpleCookie()
        try:
            cookie.load(dict(scope["headers"]).get(b"cookie", b"").decode())
            morsel = cookie.get(self.settings.session_cookie_name)
            sid = morsel.value if morsel else ""
            if len(sid) != 43:
                sid = ""
            data = await self.store.get(sid) if sid else None
        except Exception:
            response = JSONResponse({"detail": "Session service unavailable"}, status_code=503)
            return await response(scope, receive, send)
        scope["session"] = data or {"csrf_token": secrets.token_urlsafe(32)}
        scope.setdefault("state", {})
        current_sid = sid if data else secrets.token_urlsafe(32)
        original = json.dumps(scope["session"], sort_keys=True)

        async def send_with_cookie(message):
            if message["type"] == "http.response.start":
                nonlocal current_sid
                modified = (
                    not data
                    or original != json.dumps(scope["session"], sort_keys=True)
                    or scope["state"].get("rotate_session")
                )
                try:
                    if scope["state"].get("rotate_session"):
                        current_sid = secrets.token_urlsafe(32)
                    if modified and not await self.store.put(
                        current_sid, scope["session"], old_sid=sid if data else None
                    ):
                        raise RuntimeError("Session was revoked")
                except Exception:
                    message = {
                        "type": "http.response.start",
                        "status": 503,
                        "headers": [(b"content-type", b"application/json")],
                    }
                    # Session persistence is a prerequisite for authentication.
                    scope["state"]["session_failed"] = True
                else:
                    response = JSONResponse({})
                    response.set_cookie(
                        self.settings.session_cookie_name,
                        current_sid,
                        max_age=self.settings.session_ttl_seconds,
                        httponly=True,
                        secure=self.settings.app_env == "production",
                        samesite="lax",
                        path="/",
                    )
                    if modified:
                        message["headers"].extend([(b"set-cookie", response.headers["set-cookie"].encode())])
                    message["headers"].extend(
                        [
                            (b"cache-control", b"no-store"),
                            (b"x-content-type-options", b"nosniff"),
                            (b"referrer-policy", b"same-origin"),
                        ]
                    )
            elif message["type"] == "http.response.body" and scope["state"].get("session_failed"):
                message = {
                    "type": "http.response.body",
                    "body": b'{"detail":"Session service unavailable"}',
                    "more_body": False,
                }
            await send(message)

        await self.app(scope, receive, send_with_cookie)


def current_user(request: Request) -> User:
    value = request.session.get("user")
    if not value:
        raise HTTPException(401, "Sign in to continue")
    return User.model_validate(value)


def candidate_user(request: Request) -> User:
    user = current_user(request)
    if user.role != "candidate":
        raise HTTPException(403, "Candidate access required")
    return user


def hr_user(request: Request) -> User:
    user = current_user(request)
    if user.role != "hr":
        raise HTTPException(403, "HR access required")
    return user


def require_csrf(request: Request):
    expected = request.session.get("csrf_token", "")
    actual = request.headers.get("x-csrf-token", "")
    if not actual or not expected or not secrets.compare_digest(actual, expected):
        raise HTTPException(403, "Invalid CSRF token")
    origin = request.headers.get("origin")
    allowed = request.app.state.settings.cors_origins + [
        request.app.state.settings.frontend_url,
        request.app.state.settings.backend_url,
    ]
    if origin and origin not in allowed:
        raise HTTPException(403, "Request origin is not allowed")


class OIDC:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.oauth = OAuth()
        if settings.linkedin_client_id and settings.linkedin_client_secret:
            self.oauth.register(
                "linkedin",
                client_id=settings.linkedin_client_id,
                client_secret=settings.linkedin_client_secret,
                server_metadata_url=settings.linkedin_discovery_url,
                client_cls=LinkedInOAuthApp,
                client_kwargs={"scope": "openid profile email", "token_endpoint_auth_method": "client_secret_post"},
            )
        if settings.entra_tenant_id and settings.entra_client_id and settings.entra_client_secret:
            self.oauth.register(
                "hr",
                client_id=settings.entra_client_id,
                client_secret=settings.entra_client_secret,
                server_metadata_url=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0/.well-known/openid-configuration",
                client_kwargs={"scope": "openid profile email"},
            )

    def client(self, provider: Literal["linkedin", "hr"]):
        client = self.oauth.create_client(provider)
        if client is None:
            raise ConfigurationError(f"{provider.title()} authentication is not configured")
        return client

    async def login(self, request: Request, provider: Literal["linkedin", "hr"]):
        return_to = oauth_return_path(request.query_params.get("return_to"), provider)
        client = self.client(provider)
        uri = self.settings.linkedin_redirect_uri if provider == "linkedin" else self.settings.entra_redirect_uri
        # Authlib generates unpredictable state and nonce. The destination is
        # bound to this specific authorization attempt, never a global value.
        authorization = await client.create_authorization_url(uri, nonce=secrets.token_urlsafe(32))
        await client.save_authorize_data(request, redirect_uri=uri, return_to=return_to, **authorization)
        return RedirectResponse(authorization["url"], status_code=302)

    def identity(self, claims: dict, provider: str) -> User:
        issuer = (
            self.settings.linkedin_issuer
            if provider == "linkedin"
            else f"https://login.microsoftonline.com/{self.settings.entra_tenant_id}/v2.0"
        )
        if claims.get("iss") != issuer or not claims.get("sub"):
            raise HTTPException(401, "Invalid identity claims")
        if provider == "hr":
            allowed = {*self.settings.hr_allowed_roles, self.settings.entra_hr_role}
            if claims.get("tid") != self.settings.entra_tenant_id or not allowed.intersection(claims.get("roles", [])):
                raise HTTPException(403, "The configured HR application role is required")
        name = claims.get("name")
        email = claims.get("email") or (claims.get("preferred_username") if provider == "hr" else None)
        profile = None
        if provider == "linkedin":
            # LinkedIn profile/contact claims are optional. Authentication is
            # bound to the validated issuer/subject; the application form
            # collects required contact details rather than inventing them.
            profile = linkedin_profile(claims, issuer)
            name = profile.name or ""
            if not name:
                name = " ".join(value for value in (profile.given_name, profile.family_name) if value)
            email = profile.email or ""
        elif not name or not email:
            raise HTTPException(401, "Identity is missing required profile information")
        return User(
            sub=claims["sub"],
            name=name,
            email=email,
            issuer=issuer,
            role="candidate" if provider == "linkedin" else "hr",
            linkedin_profile=profile,
        )

    async def callback(self, request: Request, provider: Literal["linkedin", "hr"]):
        client = self.client(provider)
        issuer = (
            self.settings.linkedin_issuer
            if provider == "linkedin"
            else f"https://login.microsoftonline.com/{self.settings.entra_tenant_id}/v2.0"
        )
        try:
            state_data = await client.framework.get_state_data(request.session, request.query_params.get("state"))
            if not state_data or not state_data.get("nonce"):
                raise HTTPException(401, "Authentication state is missing or expired")
            return_to = oauth_return_path(state_data.get("return_to"), provider)
            token = await client.authorize_access_token(
                request,
                claims_options={
                    "iss": {"essential": True, "value": issuer},
                    "aud": {"essential": True, "value": client.client_id},
                },
            )
            if "id_token" not in token or not token.get("userinfo"):
                raise HTTPException(401, "OIDC identity token is required")
            claims = dict(token["userinfo"])
            # LinkedIn omits nonce in some code-flow tokens. When present it
            # must still match, even if a token claims nonce_supported=false.
            if (provider != "linkedin" or "nonce" in claims) and not secrets.compare_digest(
                str(claims.get("nonce", "")), state_data["nonce"]
            ):
                raise HTTPException(401, "Invalid identity nonce")
            if provider == "linkedin":
                profile = await client.userinfo(token=token)
                if not isinstance(profile.get("sub"), str) or not profile["sub"] or profile["sub"] != claims.get("sub"):
                    raise HTTPException(401, "LinkedIn profile does not match the identity token")
                if profile.get("email") is not None and profile["email"] != claims.get("email"):
                    # Verification refers to a particular mailbox. A token's
                    # flag cannot verify a different userinfo contact address.
                    claims.pop("email_verified", None)
                # The profile response cannot replace validated token claims.
                claims.update(
                    {
                        field: profile[field]
                        for field in ("name", "given_name", "family_name", "picture", "locale", "email", "email_verified")
                        if profile.get(field) is not None
                    }
                )
            user = self.identity(claims, provider)
        except HTTPException:
            raise
        except Exception as exc:
            oauth_error = getattr(exc, "error", "")
            if not isinstance(oauth_error, str) or oauth_error not in {
                "invalid_client", "invalid_grant", "invalid_scope", "unauthorized_client",
                "access_denied", "invalid_request",
            }:
                oauth_error = "unclassified"
            claim = getattr(exc, "claim_name", getattr(exc, "claim", ""))
            if not isinstance(claim, str) or claim not in {
                "iss", "aud", "exp", "iat", "nbf", "nonce", "azp", "at_hash", "sub",
            }:
                claim = "-"
            logging.getLogger("uvicorn.error").warning(
                "OIDC callback failure: provider=%s type=%s error=%s claim=%s",
                provider, type(exc).__name__, oauth_error, claim,
            )
            raise HTTPException(401, "Authentication callback could not be validated") from None
        request.session.clear()
        request.session.update(user=user.model_dump(), csrf_token=secrets.token_urlsafe(32))
        request.state.rotate_session = True
        request.state.oauth_return_to = return_to
        return user
