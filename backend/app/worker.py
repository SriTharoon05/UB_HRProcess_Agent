"""Run separately with python -m app.worker. Redis persistence is required."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

from arq import Retry, cron
from arq.connections import RedisSettings
from arq.worker import run_worker

from app.config import get_settings
from app.errors import IntegrationError
from app.models import Evaluation, Job
from app.queue import SubmissionCoordinator
from app.services.ai import AIService
from app.metadata import SQLiteMetadata
from app.services.sqlite_d365 import connected_adapter
from app.services.resumes import ResumeService

logger = logging.getLogger(__name__)


async def worker_startup(ctx):
    settings = get_settings()
    if settings.demo_mode:
        raise RuntimeError("The durable worker requires DEMO_MODE=false; demo evaluations are explicit fixtures")
    ctx.update(
        settings=settings, adapter=connected_adapter(settings), resumes=ResumeService(settings), ai=AIService(settings)
    )
    metadata = getattr(ctx["adapter"], "metadata", None)
    if isinstance(metadata, SQLiteMetadata):
        await metadata.initialize()
        ctx["metadata"] = metadata
    ctx["coordinator"] = SubmissionCoordinator(settings, ctx["adapter"], ctx["resumes"], ctx["redis"])
    await ctx["coordinator"].reconcile()


async def recover_submissions(ctx):
    await ctx["coordinator"].reconcile()


async def evaluate_application(
    ctx, application_id: str, resume_ref: str, filename: str, requirement_id: str, job_snapshot: dict
):
    settings, redis = ctx["settings"], ctx["redis"]
    key = f"{settings.redis_prefix}:evaluation:{application_id}"
    metadata = ctx.get("metadata") or getattr(ctx["adapter"], "metadata", None)
    metadata = metadata if isinstance(metadata, SQLiteMetadata) else None

    async def persist(state):
        if metadata:
            await metadata.save_evaluation_state(application_id, state)
        else:
            await redis.set(key, json.dumps(state), ex=settings.retention_days * 86400)

    lock = redis.lock(key + ":lock", timeout=600, blocking_timeout=0)
    if not await lock.acquire():
        raise Retry(defer=30)
    try:
        if metadata:
            record = await metadata.get_application(application_id, settings.d365_company)
            if not record or record["stage"] not in {"accepted", "queued"}:
                raise IntegrationError("Evaluation lacks an acknowledged application", retryable=False)
            if (resume_ref != record["resume_ref"] or filename != record["resume_file_name"]
                    or requirement_id != record["requirement_id"] or job_snapshot != record["job_snapshot"]):
                raise IntegrationError("Evaluation task does not match its frozen SQLite snapshot", retryable=False)
            state = await metadata.get_evaluation_state(application_id) or {}
        else:
            previous = await redis.get(key)
            state = json.loads(previous) if previous else {}
        if state.get("status") == "Completed":
            return {"status": "already_completed"}
        attempt = int(ctx.get("job_try", 1))
        state.update(status="Processing", attempt=attempt)
        await persist(state)
        try:
            if state.get("evaluation"):
                evaluation = Evaluation.model_validate(state["evaluation"])
            else:
                if not resume_ref or not application_id or not requirement_id:
                    raise IntegrationError("Evaluation task is missing required references", retryable=False)
                job = Job.model_validate(job_snapshot)
                if job.requirement_id != requirement_id:
                    raise IntegrationError("Job snapshot does not match evaluation task", retryable=False)
                data = await ctx["resumes"].read(resume_ref)
                state["resume_sha256"] = hashlib.sha256(data).hexdigest()
                if metadata and state["resume_sha256"] != record["payload"]["resume_sha256"]:
                    raise IntegrationError("Resume bytes differ from the submitted snapshot", retryable=False)
                state["jd_hash"] = hashlib.sha256(job.model_dump_json().encode()).hexdigest()
                text = await asyncio.to_thread(ctx["resumes"].extract, data, filename)
                evaluation = await ctx["ai"].evaluate(text, job)
                state["evaluation"] = evaluation.model_dump()
                # Reuse validated output after a D365 write failure, so retries
                # do not regenerate a different score or incur duplicate AI calls.
                await persist(state)
            await ctx["adapter"].save_candidate_evaluation(
                {
                    "application_id": application_id,
                    "requirement_id": requirement_id,
                    "evaluation": evaluation.model_dump(),
                    "evaluation_date": state.setdefault("evaluation_date", datetime.now(timezone.utc).isoformat()),
                    "jd_hash": state.get("jd_hash", ""),
                    "resume_sha256": state.get("resume_sha256", ""),
                    "idempotency_key": f"{application_id}:{evaluation.prompt_version}:{evaluation.rubric_version}",
                }
            )
            if metadata:
                # The adapter also commits the confirmed evaluation identifiers/date.
                state.update(await metadata.get_evaluation_state(application_id) or {})
                state["evaluation_confirmed"] = True
            state["status"] = "Completed"
            await persist(state)
            return {"status": "completed"}
        except Exception as exc:
            if metadata:
                state.update(await metadata.get_evaluation_state(application_id) or {})
            retryable = isinstance(exc, IntegrationError) and exc.retryable
            state["status"] = "Retrying" if retryable and attempt < settings.evaluation_max_attempts else "Failed"
            # Preserve only safe category codes, never provider responses.
            state["error_code"] = "integration_error" if isinstance(exc, IntegrationError) else "processing_error"
            await persist(state)
            logger.warning("evaluation_attempt_failed", extra={"attempt": attempt, "retryable": retryable})
            if retryable and attempt < settings.evaluation_max_attempts:
                raise Retry(defer=min(300, 10 * 2 ** (attempt - 1))) from None
            return {"status": "failed"}
    finally:
        await lock.release()


class WorkerSettings:
    functions = [evaluate_application]
    cron_jobs = [cron(recover_submissions, minute=set(range(60)), unique=True)]
    on_startup = worker_startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 540
    max_tries = get_settings().evaluation_max_attempts
    keep_result = 86400
    retry_jobs = True


if __name__ == "__main__":
    run_worker(WorkerSettings)
