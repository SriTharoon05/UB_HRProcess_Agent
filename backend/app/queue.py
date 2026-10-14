"""Submission coordination. Connected screenshot contracts keep a SQLite outbox.

Redis transports jobs and provides locks; the SQLite snapshot survives queue loss.
The explicitly selected legacy contract retains its previous Redis behavior.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.errors import IntegrationError
from app.metadata import SQLiteMetadata, encode

logger = logging.getLogger(__name__)


class SubmissionCoordinator:
    def __init__(self, settings, adapter, resumes, redis=None):
        self.settings, self.adapter, self.resumes, self.redis = settings, adapter, resumes, redis
        metadata = getattr(adapter, "metadata", None)
        self.metadata = metadata if isinstance(metadata, SQLiteMetadata) else None
        self.memory = {}
        self.locks = {}

    def key(self, user, idempotency_key):
        if self.metadata:
            scope = [self.settings.d365_company, user.issuer, user.sub, idempotency_key]
            digest = hashlib.sha256(encode(scope).encode()).hexdigest()
        else:
            # Keep existing Redis keys discoverable in explicitly selected
            # legacy mode when upgrading an already running deployment.
            digest = hashlib.sha256(f"{user.issuer}|{user.sub}|{idempotency_key}".encode()).hexdigest()
        return f"{self.settings.redis_prefix}:submission:{digest}"

    async def load(self, key):
        if self.metadata:
            return await self.metadata.get_submission(key)
        if self.redis:
            value = await self.redis.get(key)
            return json.loads(value) if value else None
        return self.memory.get(key)

    async def persist(self, key, record):
        if self.metadata:
            await self.metadata.update_submission(key, record)
            return
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
            if self.metadata and result["application_id"] != record["application_id"]:
                raise IntegrationError("D365 changed the frozen ApplicationId", retryable=False)
            record.update(application_id=str(result["application_id"]), stage="accepted")
            if self.metadata:
                record.update(candidate_id=result["candidate_id"], hr_status="Submitted")
            await self.persist(key, record)
        if record["stage"] == "accepted":
            await self.enqueue(key, record)
        state = await self.metadata.get_evaluation_state(record["application_id"]) if self.metadata else None
        return {
            "success": True,
            "application_id": record["application_id"],
            "ai_status": "Completed" if self.settings.demo_mode else (state or {}).get("status", "Pending"),
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
                "idempotency_key": key.rsplit(":", 1)[-1] if self.metadata
                else hashlib.sha256((key + fingerprint + job_hash).encode()).hexdigest(),
            }
            if user.linkedin_profile is not None:
                # This snapshot comes from validated provider data, not editable
                # form fields. Retry the recorded first submission unchanged.
                payload["linkedin_profile"] = user.linkedin_profile.model_dump(mode="json", exclude_none=True)
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
            if self.metadata:
                application_id = "APP-" + str(uuid.uuid4())
                payload["application_id"] = application_id
                record.update(application_id=application_id, company=self.settings.d365_company,
                              payload_sha256=hashlib.sha256(encode(payload).encode()).hexdigest())
                try:
                    record, created = await self.metadata.reserve(key, record)
                except Exception:
                    await self.resumes.delete(resume_ref)
                    raise
                if not created:
                    # A competing process reserved the immutable input first.
                    await self.resumes.delete(resume_ref)
            else:
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
        if self.metadata:
            entries = await self.metadata.submissions(company=self.settings.d365_company)
        else:
            entries = [(key.decode() if isinstance(key, bytes) else key, None)
                       async for key in self.redis.scan_iter(match=f"{self.settings.redis_prefix}:submission:*")]
        for key, _ in entries:
            if key.endswith(":lock"):
                continue
            record = await self.load(key)
            if not record or record.get("stage") not in {"ready", "accepted", "queued"}:
                continue
            if record["stage"] == "queued":
                application_id = record["application_id"]
                if self.metadata:
                    state = await self.metadata.get_evaluation_state(application_id) or {}
                else:
                    evaluation = await self.redis.get(f"{self.settings.redis_prefix}:evaluation:{application_id}")
                    state = json.loads(evaluation) if evaluation else {}
                if state.get("status") in {"Completed", "Failed"}:
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
                    logger.warning("submission_recovery_pending")
                finally:
                    await lock.release()


def submission_fingerprint(requirement_id, data, phone, linkedin_url, consent_version, *, candidate_name=None, email=None):
    fields = [requirement_id, phone, linkedin_url, consent_version]
    if candidate_name is not None or email is not None:
        fields.extend([candidate_name, email])
    metadata = json.dumps(fields, separators=(",", ":"))
    return hashlib.sha256(metadata.encode() + b"\0" + data).hexdigest()
