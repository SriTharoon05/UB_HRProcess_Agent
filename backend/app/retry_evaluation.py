"""Explicit operator recovery: python -m app.retry_evaluation APPLICATION_ID.

Run after fixing credentials/service paths. Completed records are never rerun;
validated cached AI output is preserved so only the failed D365 write retries.
"""

import argparse
import asyncio
import json

from arq.connections import RedisSettings, create_pool

from app.config import get_settings


async def retry(application_id, settings=None):
    settings = settings or get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    key = f"{settings.redis_prefix}:evaluation:{application_id}"
    try:
        value = await redis.get(key)
        state = json.loads(value) if value else {}
        if state.get("status") == "Completed":
            return "Already completed; no evaluation was queued."
        records = []
        async for submission_key in redis.scan_iter(match=f"{settings.redis_prefix}:submission:*"):
            if submission_key.decode().endswith(":lock"):
                continue
            data = await redis.get(submission_key)
            record = json.loads(data) if data else {}
            if record.get("application_id") == application_id:
                records.append(record)
        if len(records) != 1:
            raise RuntimeError("Exactly one retained submission is required for safe recovery")
        lock = redis.lock(key + ":lock", timeout=30, blocking_timeout=0)
        if not await lock.acquire():
            raise RuntimeError("An evaluation is running; retry later")
        try:
            value = await redis.get(key)
            state = json.loads(value) if value else {}
            if state.get("status") == "Completed":
                return "Already completed; no evaluation was queued."
            if await redis.exists(f"arq:job:evaluation:{application_id}"):
                raise RuntimeError("An evaluation is already queued; no duplicate was created")
            await redis.delete(f"arq:result:evaluation:{application_id}")
            state.update(status="Pending", attempt=0)
            state.pop("error_code", None)
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
            return "Evaluation queued using retained references and cached validated output."
        finally:
            await lock.release()
    finally:
        await redis.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_id")
    args = parser.parse_args()
    print(asyncio.run(retry(args.application_id)))
