import hashlib
import json
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Annotated, Literal
from urllib.parse import urlparse

from arq.connections import RedisSettings, create_pool
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict

from app.auth import OIDC, OpaqueSessionMiddleware, SessionStore, candidate_user, hr_user, require_csrf
from app.config import Settings, get_settings
from app.demo import DemoAdapter
from app.errors import IntegrationError, ResumeValidationError
from app.models import Application, User
from app.queue import SubmissionCoordinator, submission_fingerprint
from app.services.d365 import D365Service
from app.services.resumes import ResumeService

logger = logging.getLogger(__name__)


class BodyLimitMiddleware:
    """Bound multipart request bytes before Starlette can spool arbitrary uploads."""

    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/applications" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                response = JSONResponse({"detail": "Resume upload exceeds the size limit"}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body"):
                break
        index = 0

        async def replay():
            nonlocal index
            if index < len(chunks):
                message = chunks[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay, send)


class DemoLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["candidate", "hr"]


def validate_application_contact(candidate_name: str, email: str) -> tuple[str, str]:
    """Validate application contact without treating it as authenticated identity."""
    candidate_name, email = candidate_name.strip(), email.strip()
    if (
        not candidate_name
        or len(candidate_name) > 200
        or not candidate_name.isprintable()
        or not any(character.isalpha() for character in candidate_name)
    ):
        raise HTTPException(422, "Enter your full name using up to 200 characters")
    local, separator, domain = email.partition("@")
    atom = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    labels = domain.split(".")
    if (
        not separator
        or len(email) > 320
        or len(local) > 64
        or len(domain) > 253
        or not re.fullmatch(atom + r"(?:\." + atom + r")*", local)
        or len(labels) < 2
        or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
    ):
        raise HTTPException(422, "Enter a valid contact email using up to 320 characters")
    return candidate_name, email


class RateLimiter:
    def __init__(self, settings, redis=None):
        self.settings, self.redis = settings, redis
        self.memory = {}

    async def check(self, request, upload=False):
        address = request.client.host if request.client else "unknown"
        # Do not trust forwarded headers supplied by public clients.
        bucket = int(time.time() // 60)
        key = f"{self.settings.redis_prefix}:rate:{hashlib.sha256(address.encode()).hexdigest()}:{'upload' if upload else 'public'}:{bucket}"
        if self.redis:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, 65)
        else:
            self.memory = {k: v for k, v in self.memory.items() if k.endswith(f":{bucket}")}
            count = self.memory.get(key, 0) + 1
            self.memory[key] = count
        limit = self.settings.upload_rate_limit if upload else self.settings.public_rate_limit
        if count > limit:
            raise HTTPException(429, "Too many requests. Please try again shortly.", headers={"Retry-After": "60"})


def create_app(settings: Settings | None = None):
    settings = settings or get_settings()
    session_store = SessionStore(settings)

    @asynccontextmanager
    async def lifespan(app):
        if not settings.demo_mode:
            app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await app.state.redis.ping()
            session_store.redis = app.state.redis
            app.state.coordinator.redis = app.state.redis
            app.state.limiter.redis = app.state.redis
        yield
        if app.state.redis:
            await app.state.redis.aclose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.redis = None
    app.state.adapter = DemoAdapter() if settings.demo_mode else D365Service(settings)
    app.state.resumes = ResumeService(settings)
    app.state.coordinator = SubmissionCoordinator(settings, app.state.adapter, app.state.resumes)
    app.state.limiter = RateLimiter(settings)
    app.state.oidc = OIDC(settings)
    app.add_middleware(BodyLimitMiddleware, max_bytes=(settings.max_resume_size_mb + 1) * 1024 * 1024)
    app.add_middleware(OpaqueSessionMiddleware, settings=settings, store=session_store)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )

    @app.exception_handler(IntegrationError)
    async def integration_error(request, exc):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"detail": "Request validation failed. Check the required fields and file type."}, status_code=422
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error("request_failed", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            {"detail": "The service could not complete this request. Please try again."}, status_code=503
        )

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "demo_mode": settings.demo_mode, "app_name": settings.app_name}

    @app.get("/api/auth/me")
    async def auth_me(request: Request):
        return {
            "user": request.session.get("user"),
            "csrf_token": request.session["csrf_token"],
            "demo_mode": settings.demo_mode,
            "consent_version": settings.consent_version,
        }

    @app.post("/api/auth/demo", dependencies=[Depends(require_csrf)])
    async def demo_login(body: DemoLogin, request: Request):
        await app.state.limiter.check(request)
        if not settings.demo_mode or settings.app_env == "production":
            raise HTTPException(404, "Demo authentication is unavailable")
        user = User(
            sub="demo-candidate" if body.role == "candidate" else "demo-hr",
            name="Maya Chen" if body.role == "candidate" else "Avery Morgan",
            email="maya.chen@example.test" if body.role == "candidate" else "avery.morgan@example.test",
            role=body.role,
            issuer="fictional-demo",
        )
        request.session.clear()
        request.session.update(user=user.model_dump(), csrf_token=secrets.token_urlsafe(32))
        request.state.rotate_session = True
        return {
            "user": user,
            "csrf_token": request.session["csrf_token"],
            "demo_mode": True,
            "consent_version": settings.consent_version,
        }

    @app.post("/api/auth/logout", dependencies=[Depends(require_csrf)])
    async def logout(request: Request):
        request.session.clear()
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        request.state.rotate_session = True
        return {"success": True}

    @app.get("/auth/{provider}/login")
    async def oidc_login(provider: Literal["linkedin", "hr"], request: Request):
        await app.state.limiter.check(request)
        return await app.state.oidc.login(request, provider)

    @app.get("/auth/{provider}/callback")
    async def oidc_callback(provider: Literal["linkedin", "hr"], request: Request):
        await app.state.oidc.callback(request, provider)
        return RedirectResponse(
            settings.frontend_url.rstrip("/") + ("/candidate/applications" if provider == "linkedin" else "/hr"),
            status_code=303,
        )

    async def jobs_list(request, search, department, location, work_mode, employment_type):
        await app.state.limiter.check(request)
        jobs = await app.state.adapter.get_open_requirements()
        jobs = [job for job in jobs if job.status.casefold() == "open"]
        for field, value in [
            ("department", department),
            ("location", location),
            ("work_mode", work_mode),
            ("employment_type", employment_type),
        ]:
            if value:
                jobs = [j for j in jobs if value.casefold() in getattr(j, field).casefold()]
        if search:
            needle = search.casefold()
            jobs = [
                j
                for j in jobs
                if needle in " ".join([j.title, j.description, j.department, *j.required_skills]).casefold()
            ]
        return jobs

    @app.get("/api/jobs")
    async def jobs(
        request: Request,
        search: str = "",
        department: str = "",
        location: str = "",
        work_mode: str = "",
        employment_type: str = "",
    ):
        return await jobs_list(request, search, department, location, work_mode, employment_type)

    @app.get("/api/hr/jobs", dependencies=[Depends(hr_user)])
    async def hr_jobs(
        request: Request,
        search: str = "",
        department: str = "",
        location: str = "",
        work_mode: str = "",
        employment_type: str = "",
    ):
        return await jobs_list(request, search, department, location, work_mode, employment_type)

    async def get_job(requirement_id):
        jobs = await app.state.adapter.get_open_requirements()
        job = next((j for j in jobs if j.requirement_id == requirement_id and j.status.casefold() == "open"), None)
        if not job:
            raise HTTPException(404, "Open job requirement not found")
        return job

    @app.get("/api/jobs/{requirement_id}")
    async def job_detail(requirement_id: str, request: Request):
        await app.state.limiter.check(request)
        return await get_job(requirement_id)

    @app.post("/api/applications", dependencies=[Depends(require_csrf)])
    async def submit_application(
        request: Request,
        user: Annotated[User, Depends(candidate_user)],
        requirement_id: Annotated[str, Form()],
        resume: Annotated[UploadFile, File()],
        candidate_name: Annotated[str | None, Form()] = None,
        email: Annotated[str | None, Form()] = None,
        phone: Annotated[str, Form()] = "",
        linkedin_url: Annotated[str, Form()] = "",
        consent_accepted: Annotated[bool, Form()] = False,
        consent_version: Annotated[str, Form()] = "",
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        await app.state.limiter.check(request, upload=True)
        if not idempotency_key or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", idempotency_key):
            raise HTTPException(422, "A stable Idempotency-Key of 8 to 128 characters is required")
        if not consent_accepted or consent_version != settings.consent_version:
            raise HTTPException(422, "Accept the current consent notice before applying")
        form = await request.form()
        candidate_name, email = validate_application_contact(
            (candidate_name or "") if "candidate_name" in form else user.name,
            (email or "") if "email" in form else user.email,
        )
        application_user = user.model_copy(update={"name": candidate_name, "email": email})
        if len(phone) > 30 or not re.fullmatch(r"[0-9+() .-]*", phone):
            raise HTTPException(422, "Enter a valid phone number")
        if linkedin_url:
            parsed = urlparse(linkedin_url)
            if (
                len(linkedin_url) > 500
                or parsed.scheme != "https"
                or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}
                or parsed.username
                or parsed.password
            ):
                raise HTTPException(422, "LinkedIn profile must be an HTTPS linkedin.com URL")
        job = await get_job(requirement_id)
        if job.deadline:
            try:
                deadline = datetime.fromisoformat(job.deadline.replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                if deadline < datetime.now(timezone.utc):
                    raise HTTPException(409, "This job requirement is no longer accepting applications")
            except ValueError:
                raise IntegrationError(
                    "Job service returned an invalid application deadline", retryable=False
                ) from None
        data = await resume.read(settings.max_resume_size_mb * 1024 * 1024 + 1)
        filename = PurePath((resume.filename or "resume").replace("\\", "/")).name
        if len(filename) > 150 or any(ord(c) < 32 for c in filename):
            raise HTTPException(422, "Resume filename is invalid")
        try:
            app.state.resumes.validate_upload(data, filename, resume.content_type or "")
        except ResumeValidationError as exc:
            raise HTTPException(422, str(exc)) from None
        fingerprint = submission_fingerprint(
            requirement_id, data, phone, linkedin_url, consent_version, candidate_name=candidate_name, email=email
        )
        return await app.state.coordinator.submit(
            application_user, idempotency_key, fingerprint, job, data, filename, phone, linkedin_url, consent_version
        )

    async def processing_status(record):
        if app.state.redis:
            value = await app.state.redis.get(f"{settings.redis_prefix}:evaluation:{record.application_id}")
            if value:
                record = record.model_copy(update={"ai_status": json.loads(value)["status"]})
        return record

    @app.get("/api/me/applications")
    async def my_applications(user: Annotated[User, Depends(candidate_user)]):
        records = await app.state.adapter.get_my_applications(user)
        result = []
        for record in records:
            if record.owner_sub != user.sub or record.owner_issuer != user.issuer:
                raise IntegrationError("Application service returned an invalid ownership scope", retryable=False)
            record = await processing_status(record)
            result.append(Application.model_validate(record.model_dump()))
        return result

    @app.get("/api/applications/{application_id}")
    async def own_application(application_id: str, user: Annotated[User, Depends(candidate_user)]):
        record = await app.state.adapter.get_application(application_id)
        if record.owner_sub != user.sub or record.owner_issuer != user.issuer:
            raise HTTPException(404, "Application not found")
        return Application.model_validate((await processing_status(record)).model_dump())

    @app.get("/api/hr/jobs/{requirement_id}/candidates", dependencies=[Depends(hr_user)])
    async def candidates(requirement_id: str, limit: int = 25):
        if limit < 1 or limit > 100:
            raise HTTPException(422, "Candidate limit must be between 1 and 100")
        job = await get_job(requirement_id)
        records = await app.state.adapter.get_top_candidates(requirement_id, limit)
        records = [c.model_copy(update={"job_title": c.job_title or job.title}) for c in records]
        return {
            "candidates": [(await processing_status(record)).public_dict() for record in records],
            "limit": limit,
            "returned_count": len(records),
        }

    @app.get("/api/hr/jobs/{requirement_id}/candidates/{application_id}", dependencies=[Depends(hr_user)])
    async def candidate_detail(requirement_id: str, application_id: str):
        if not settings.demo_mode and not settings.d365_application_path:
            records = await app.state.adapter.get_top_candidates(requirement_id, 100)
            record = next((c for c in records if c.application_id == application_id), None)
            if not record:
                raise HTTPException(404, "Candidate not returned in this requirement's ranked results")
        else:
            record = await app.state.adapter.get_application(application_id)
        if record.requirement_id != requirement_id:
            raise HTTPException(404, "Candidate not found for this requirement")
        return (await processing_status(record)).public_dict()

    @app.get("/api/hr/applications/{application_id}/resume", dependencies=[Depends(hr_user)])
    async def resume_download(application_id: str, requirement_id: str = ""):
        if not settings.demo_mode and not settings.d365_application_path:
            if not requirement_id:
                raise HTTPException(422, "A requirement_id is required to resolve this resume from ranked candidates")
            records = await app.state.adapter.get_top_candidates(requirement_id, 100)
            record = next(
                (c for c in records if c.application_id == application_id and c.requirement_id == requirement_id), None
            )
            if not record:
                raise HTTPException(404, "Candidate not returned in this requirement's ranked results")
        else:
            record = await app.state.adapter.get_application(application_id)
        if not record.resume_ref:
            raise HTTPException(
                404, "The fictional sample has no real resume. Submit a demo application to preview an upload."
            )
        data = await app.state.resumes.read(record.resume_ref)
        filename = PurePath(record.resume_file_name.replace("\\", "/")).name
        filename = re.sub(r"[^a-zA-Z0-9_. -]", "_", filename)[:150] or "resume"
        media_type = (
            "application/pdf"
            if filename.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return Response(
            data,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"},
        )

    return app


app = create_app()
