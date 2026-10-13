"""Durable submission outbox and idempotency state, never a business database.

D365 must implement a unique IdempotencyKey constraint for crash-safe submission.
Redis retains only temporary processing state and references to private resumes.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.errors import IntegrationError


class SubmissionCoordinator:
    def __init__(self, settings, adapter, resumes, redis=None):
        self.settings, self.adapter, self.resumes, self.redis = settings, adapter, resumes, redis
        self.memory = {}
        self.locks = {}

    def key(self, user, idempotency_key):
        digest = hashlib.sha256(f"{user.issuer}|{user.sub}|{idempotency_key}".encode()).hexdigest()
        return f"{self.settings.redis_prefix}:submission:{digest}"

    async def load(self, key):
        if self.redis:
            value = await self.redis.get(key)
            return json.loads(value) if value else None
        return self.memory.get(key)

    async def persist(self, key, record):
        if self.redis:
            await self.redis.set(key, json.dumps(record), ex=self.settings.retention_days * 86400)
        else:
            self.memory[key] = record

    async def enqueue(self, key, record):
        if not self.redis:
            return
        # The outbox is already durable before attempting enqueue. A periodic
        # worker reconciliation recovers a crash between D365 acceptance and enqueue.
        await self.redis.enqueue_job(
            "evaluate_application",
            record["application_id"],
            record["resume_ref"],
            record["resume_file_name"],
            record["requirement_id"],
            record["job_snapshot"],
            _job_id=f"evaluation:{record['application_id']}",
            _expires=self.settings.retention_days * 86400,
        )
        record["stage"] = "queued"
        await self.persist(key, record)

    async def finish(self, key, record):
        if record["stage"] == "ready":
            result = await self.adapter.submit_application(record["payload"])
            if not result.get("application_id"):
                raise IntegrationError("Application service did not return an identifier", retryable=False)
            record.update(application_id=str(result["application_id"]), stage="accepted")
            await self.persist(key, record)
        if record["stage"] == "accepted":
            await self.enqueue(key, record)
        return {
            "success": True,
            "application_id": record["application_id"],
            "ai_status": "Completed" if self.settings.demo_mode else "Pending",
            "message": "Application submitted. Demo evaluation is a fictional sample."
            if self.settings.demo_mode
            else "Application submitted. Evidence evaluation is queued for human review.",
        }

    async def submit(
        self, user, idempotency_key, fingerprint, job, data, filename, phone, linkedin_url, consent_version
    ):
        key = self.key(user, idempotency_key)
        if self.redis:
            lock = self.redis.lock(key + ":lock", timeout=120, blocking_timeout=1)
            if not await lock.acquire():
                raise HTTPException(409, "This submission is already in progress. Retry with the same Idempotency-Key.")
        else:
            lock = self.locks.setdefault(key, asyncio.Lock())
            await lock.acquire()
        try:
            record = await self.load(key)
            if record:
                if record["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Idempotency-Key was already used for a different application")
                return await self.finish(key, record)
            resume_ref = await self.resumes.store(data, filename)
            job_hash = hashlib.sha256(job.model_dump_json().encode()).hexdigest()
            payload = {
                "requirement_id": job.requirement_id,
                "candidate_name": user.name,
                "email": user.email,
                "owner_sub": user.sub,
                "owner_issuer": user.issuer,
                "phone": phone,
                "linkedin_url": linkedin_url,
                "resume_ref": resume_ref,
                "resume_file_name": filename,
                "resume_sha256": hashlib.sha256(data).hexdigest(),
                "job_description_hash": job_hash,
                "consent_accepted": True,
                "consent_version": consent_version,
                "consent_date": datetime.now(timezone.utc).isoformat(),
                "idempotency_key": hashlib.sha256((key + fingerprint + job_hash).encode()).hexdigest(),
            }
            record = {
                "stage": "ready",
                "fingerprint": fingerprint,
                "payload": payload,
                "resume_ref": resume_ref,
                "resume_file_name": filename,
                "requirement_id": job.requirement_id,
                "job_snapshot": job.model_dump(mode="json"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                await self.persist(key, record)
            except Exception:
                await self.resumes.delete(resume_ref)
                raise
            return await self.finish(key, record)
        finally:
            try:
                if self.redis:
                    await lock.release()
                else:
                    lock.release()
            except Exception:
                pass

    async def reconcile(self):
        if not self.redis:
            return
        async for key in self.redis.scan_iter(match=f"{self.settings.redis_prefix}:submission:*"):
            key = key.decode() if isinstance(key, bytes) else key
            if key.endswith(":lock"):
                continue
            record = await self.load(key)
            if not record or record.get("stage") not in {"ready", "accepted", "queued"}:
                continue
            if record["stage"] == "queued":
                application_id = record["application_id"]
                evaluation = await self.redis.get(f"{self.settings.redis_prefix}:evaluation:{application_id}")
                if evaluation and json.loads(evaluation).get("status") in {"Completed", "Failed"}:
                    continue
                if await self.redis.exists(
                    f"arq:job:evaluation:{application_id}", f"arq:result:evaluation:{application_id}"
                ):
                    continue
                record["stage"] = "accepted"
            lock = self.redis.lock(key + ":lock", timeout=120, blocking_timeout=0)
            if await lock.acquire():
                try:
                    await self.finish(key, record)
                except Exception:
                    # Do not log candidate data or external responses. Keep
                    # durable state to permit a later recovery attempt.
                    import logging

                    logging.getLogger(__name__).warning("submission_recovery_pending")
                finally:
                    await lock.release()


def submission_fingerprint(requirement_id, data, phone, linkedin_url, consent_version, *, candidate_name=None, email=None):
    fields = [requirement_id, phone, linkedin_url, consent_version]
    if candidate_name is not None or email is not None:
        fields.extend([candidate_name, email])
    metadata = json.dumps(fields, separators=(",", ":"))
    return hashlib.sha256(metadata.encode() + b"\0" + data).hexdigest()
