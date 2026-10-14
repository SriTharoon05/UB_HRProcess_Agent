"""Explicit operator recovery: python -m app.retry_evaluation APPLICATION_ID.

Run after fixing credentials/service paths. Completed records are never rerun;
validated cached AI output is preserved so only the failed D365 write retries.
"""

import argparse
import asyncio
import json
import logging
import uuid

from arq.connections import RedisSettings, create_pool

from app.config import get_settings
from app.metadata import SQLiteMetadata
from app.observability import configure_logging, error_fields, log_context, log_event, stage


async def retry(application_id, settings=None):
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    with log_context(request_id=str(uuid.uuid4()), application_id=application_id), stage("recovery.evaluation"):
        return await _retry(application_id, settings)


async def _retry(application_id, settings):
    metadata = SQLiteMetadata(settings.sqlite_database_path) if settings.d365_contract_mode == "sqlite" else None
    if metadata:
        record = await metadata.get_application(application_id, settings.d365_company)
        if not record or record["stage"] not in {"accepted", "queued"}:
            raise RuntimeError("An acknowledged SQLite submission is required for safe recovery")
        retained_state = await metadata.get_evaluation_state(application_id) or {}
        if retained_state.get("status") == "Completed":
            log_event("recovery.evaluation", "skipped", reason="already_completed")
            return "Already completed; no evaluation was queued."
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    log_event("recovery.redis", "connected")
    key = f"{settings.redis_prefix}:evaluation:{application_id}"
    try:
        if metadata:
            state = retained_state
            records = [record]
        else:
            value = await redis.get(key)
            state = json.loads(value) if value else {}
            if state.get("status") == "Completed":
                log_event("recovery.evaluation", "skipped", reason="already_completed")
                return "Already completed; no evaluation was queued."
            records = []
            async for submission_key in redis.scan_iter(match=f"{settings.redis_prefix}:submission:*"):
                if submission_key.decode().endswith(":lock"):
                    continue
                data = await redis.get(submission_key)
                item = json.loads(data) if data else {}
                if item.get("application_id") == application_id:
                    records.append(item)
            if len(records) != 1:
                raise RuntimeError("Exactly one retained submission is required for safe recovery")
        lock = redis.lock(key + ":lock", timeout=30, blocking_timeout=0)
        if not await lock.acquire():
            log_event("recovery.lock", "rejected", reason="evaluation_running")
            raise RuntimeError("An evaluation is running; retry later")
        try:
            if metadata:
                state = await metadata.get_evaluation_state(application_id) or {}
            else:
                value = await redis.get(key)
                state = json.loads(value) if value else {}
            if state.get("status") == "Completed":
                log_event("recovery.evaluation", "skipped", reason="already_completed")
                return "Already completed; no evaluation was queued."
            if await redis.exists(f"arq:job:evaluation:{application_id}"):
                log_event("recovery.evaluation", "rejected", reason="already_queued")
                raise RuntimeError("An evaluation is already queued; no duplicate was created")
            await redis.delete(f"arq:result:evaluation:{application_id}")
            state.update(status="Pending", attempt=0)
            state.pop("error_code", None)
            if metadata:
                await metadata.save_evaluation_state(application_id, state)
            else:
                await redis.set(key, json.dumps(state), ex=settings.retention_days * 86400)
            record = records[0]
            await redis.enqueue_job(
                "evaluate_application",
                application_id,
                record["resume_ref"],
                record["resume_file_name"],
                record["requirement_id"],
                record["job_snapshot"],
                _job_id=f"evaluation:{application_id}",
                _expires=settings.retention_days * 86400,
            )
            log_event("recovery.evaluation", "queued", status="Pending")
            return "Evaluation queued using retained references and cached validated output."
        finally:
            await lock.release()
    finally:
        await redis.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_id")
    args = parser.parse_args()
    try:
        print(asyncio.run(retry(args.application_id)))
    except Exception as exc:
        log_event("recovery.process", "failed", level=logging.ERROR, **error_fields(exc))
        raise SystemExit(1) from None
