import json
import secrets
from http.cookies import SimpleCookie
from typing import Literal

from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from starlette.responses import JSONResponse

from app.config import Settings
from app.errors import ConfigurationError
from app.models import User


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
                client_kwargs={"scope": "openid profile email"},
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
        client = self.client(provider)
        uri = self.settings.linkedin_redirect_uri if provider == "linkedin" else self.settings.entra_redirect_uri
        # Authlib generates and stores unpredictable state and nonce in the server-side session.
        return await client.authorize_redirect(request, uri, nonce=secrets.token_urlsafe(32))

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
        email = claims.get("email") or (claims.get("preferred_username") if provider == "hr" else None)
        if not email or not claims.get("name"):
            raise HTTPException(401, "Identity is missing required profile information")
        if provider == "linkedin" and claims.get("email_verified") is not True:
            raise HTTPException(401, "A verified LinkedIn email address is required")
        return User(
            sub=claims["sub"],
            name=claims["name"],
            email=email,
            issuer=issuer,
            role="candidate" if provider == "linkedin" else "hr",
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
            token = await client.authorize_access_token(
                request, claims_options={"iss": {"essential": True, "value": issuer}}
            )
            if "id_token" not in token or not token.get("userinfo"):
                raise HTTPException(401, "OIDC identity token is required")
            if not secrets.compare_digest(str(token["userinfo"].get("nonce", "")), state_data["nonce"]):
                raise HTTPException(401, "Invalid identity nonce")
            user = self.identity(dict(token["userinfo"]), provider)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "Authentication callback could not be validated") from None
        request.session.clear()
        request.session.update(user=user.model_dump(), csrf_token=secrets.token_urlsafe(32))
        request.state.rotate_session = True
        return user
