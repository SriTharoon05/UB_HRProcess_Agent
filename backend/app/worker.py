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
from app.services.d365 import D365Service
from app.services.resumes import ResumeService

logger = logging.getLogger(__name__)


async def worker_startup(ctx):
    settings = get_settings()
    if settings.demo_mode:
        raise RuntimeError("The durable worker requires DEMO_MODE=false; demo evaluations are explicit fixtures")
    ctx.update(
        settings=settings, adapter=D365Service(settings), resumes=ResumeService(settings), ai=AIService(settings)
    )
    ctx["coordinator"] = SubmissionCoordinator(settings, ctx["adapter"], ctx["resumes"], ctx["redis"])
    await ctx["coordinator"].reconcile()


async def recover_submissions(ctx):
    await ctx["coordinator"].reconcile()


async def evaluate_application(
    ctx, application_id: str, resume_ref: str, filename: str, requirement_id: str, job_snapshot: dict
):
    settings, redis = ctx["settings"], ctx["redis"]
    key = f"{settings.redis_prefix}:evaluation:{application_id}"
    lock = redis.lock(key + ":lock", timeout=600, blocking_timeout=0)
    if not await lock.acquire():
        raise Retry(defer=30)
    try:
        previous = await redis.get(key)
        state = json.loads(previous) if previous else {}
        if state.get("status") == "Completed":
            return {"status": "already_completed"}
        attempt = int(ctx.get("job_try", 1))
        state.update(status="Processing", attempt=attempt)
        await redis.set(key, json.dumps(state), ex=settings.retention_days * 86400)
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
                state["jd_hash"] = hashlib.sha256(job.model_dump_json().encode()).hexdigest()
                text = await asyncio.to_thread(ctx["resumes"].extract, data, filename)
                evaluation = await ctx["ai"].evaluate(text, job)
                state["evaluation"] = evaluation.model_dump()
                # Reuse validated output after a D365 write failure, so retries
                # do not regenerate a different score or incur duplicate AI calls.
                await redis.set(key, json.dumps(state), ex=settings.retention_days * 86400)
            await ctx["adapter"].save_candidate_evaluation(
                {
                    "application_id": application_id,
                    "requirement_id": requirement_id,
                    "evaluation": evaluation.model_dump(),
                    "evaluation_date": datetime.now(timezone.utc).isoformat(),
                    "jd_hash": state.get("jd_hash", ""),
                    "resume_sha256": state.get("resume_sha256", ""),
                    "idempotency_key": f"{application_id}:{evaluation.prompt_version}:{evaluation.rubric_version}",
                }
            )
            state["status"] = "Completed"
            await redis.set(key, json.dumps(state), ex=settings.retention_days * 86400)
            return {"status": "completed"}
        except Exception as exc:
            retryable = isinstance(exc, IntegrationError) and exc.retryable
            state["status"] = "Retrying" if retryable and attempt < settings.evaluation_max_attempts else "Failed"
            # Preserve only safe category codes, never provider responses.
            state["error_code"] = "integration_error" if isinstance(exc, IntegrationError) else "processing_error"
            await redis.set(key, json.dumps(state), ex=settings.retention_days * 86400)
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
