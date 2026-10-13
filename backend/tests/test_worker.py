import hashlib
import json
import os
import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from arq import Retry
from arq.connections import RedisSettings, create_pool

from app.auth import SessionStore
from app.config import Settings
from app.demo import DemoAdapter, sample_evaluation
from app.errors import ConfigurationError, IntegrationError
from app.models import User
from app.queue import SubmissionCoordinator, submission_fingerprint
from app.retry_evaluation import retry
from app.worker import evaluate_application


@pytest.fixture
async def durable_context(tmp_path):
    redis_url = os.environ.get("REDIS_TEST_URL")
    if not redis_url:
        pytest.skip("Set REDIS_TEST_URL for isolated live Redis durability tests")
    redis = await create_pool(RedisSettings.from_dsn(redis_url))
    prefix = "backend-test-" + uuid.uuid4().hex
    settings = Settings(_env_file=None, redis_url=redis_url, redis_prefix=prefix, local_resume_dir=tmp_path)
    adapter = Mock()
    adapter.submit_application = AsyncMock(return_value={"application_id": prefix + "-application"})
    adapter.save_candidate_evaluation = AsyncMock(return_value={"success": True})
    resumes = Mock()
    resumes.store = AsyncMock(return_value="azure:" + "a" * 32 + ".pdf")
    resumes.read = AsyncMock(return_value=b"resume-bytes")
    resumes.delete = AsyncMock()
    resumes.extract = Mock(return_value="Projects: built React dashboard with accessibility.")
    ai = Mock()
    ai.evaluate = AsyncMock(return_value=sample_evaluation())
    user = User(
        sub="test-sub",
        issuer="test-issuer",
        name="Fictional Applicant",
        email="fictional@example.test",
        role="candidate",
    )
    coordinator = SubmissionCoordinator(settings, adapter, resumes, redis)
    context = {
        "redis": redis,
        "settings": settings,
        "adapter": adapter,
        "resumes": resumes,
        "ai": ai,
        "job_try": 1,
        "coordinator": coordinator,
        "user": user,
        "job": DemoAdapter().jobs[0],
    }
    try:
        yield context
    finally:
        keys = []
        async for key in redis.scan_iter(match=prefix + ":*"):
            keys.append(key)
        async for key in redis.scan_iter(match=f"arq:*evaluation:{prefix}*"):
            keys.append(key)
        if keys:
            await redis.delete(*keys)
        members = await redis.zrange("arq:queue", 0, -1)
        targets = [m for m in members if m.decode().startswith("evaluation:" + prefix)]
        if targets:
            await redis.zrem("arq:queue", *targets)
        await redis.aclose()


async def submit(ctx, data=b"valid-resume", key="idempotency-001"):
    return await ctx["coordinator"].submit(
        ctx["user"],
        key,
        submission_fingerprint(ctx["job"].requirement_id, data, "", "", "v1"),
        ctx["job"],
        data,
        "resume.pdf",
        "",
        "",
        "v1",
    )


async def test_durable_outbox_idempotency_actual_references_long_job_ttl_and_recovery(durable_context):
    ctx = durable_context
    result = await submit(ctx)
    again = await submit(ctx)
    assert result["application_id"] == again["application_id"]
    ctx["adapter"].submit_application.assert_awaited_once()
    ctx["resumes"].store.assert_awaited_once()
    payload = ctx["adapter"].submit_application.call_args.args[0]
    assert payload["resume_sha256"] == hashlib.sha256(b"valid-resume").hexdigest()
    assert len(payload["job_description_hash"]) == 64 and payload["consent_accepted"] is True
    arq_key = "arq:job:evaluation:" + result["application_id"]
    assert await ctx["redis"].ttl(arq_key) > 89 * 86400
    await ctx["redis"].delete(arq_key)
    await ctx["redis"].zrem("arq:queue", "evaluation:" + result["application_id"])
    await ctx["coordinator"].reconcile()
    assert await ctx["redis"].exists(arq_key)


async def test_provider_failure_preserves_ready_outbox_without_duplicate_storage(durable_context):
    ctx = durable_context
    ctx["adapter"].submit_application.side_effect = [
        IntegrationError("Temporary upstream outage"),
        {"application_id": ctx["settings"].redis_prefix + "-application"},
    ]
    with pytest.raises(IntegrationError):
        await submit(ctx)
    key = ctx["coordinator"].key(ctx["user"], "idempotency-001")
    assert (await ctx["coordinator"].load(key))["stage"] == "ready"
    await ctx["coordinator"].reconcile()
    assert (await ctx["coordinator"].load(key))["stage"] == "queued"
    ctx["resumes"].store.assert_awaited_once()


async def test_expired_local_idempotency_cannot_evaluate_old_remote_application_with_new_resume(durable_context):
    ctx = durable_context
    remote = {}

    async def remote_submit(payload):
        remote.setdefault(
            payload["idempotency_key"], {"application_id": ctx["settings"].redis_prefix + "-app-" + str(len(remote))}
        )
        return remote[payload["idempotency_key"]]

    ctx["adapter"].submit_application.side_effect = remote_submit
    first = await submit(ctx, b"old-resume")
    await ctx["redis"].delete(ctx["coordinator"].key(ctx["user"], "idempotency-001"))
    second = await submit(ctx, b"new-resume")
    assert first["application_id"] != second["application_id"]
    assert len(remote) == 2


async def test_worker_retries_d365_write_reuses_validated_ai_and_is_idempotent(durable_context):
    ctx = durable_context
    application_id = ctx["settings"].redis_prefix + "-application"
    args = (
        application_id,
        "azure:" + "a" * 32 + ".pdf",
        "resume.pdf",
        ctx["job"].requirement_id,
        ctx["job"].model_dump(),
    )
    ctx["adapter"].save_candidate_evaluation.side_effect = [
        IntegrationError("Temporary write failure"),
        {"success": True},
    ]
    with pytest.raises(Retry):
        await evaluate_application(ctx, *args)
    state_key = f"{ctx['settings'].redis_prefix}:evaluation:{application_id}"
    assert json.loads(await ctx["redis"].get(state_key))["status"] == "Retrying"
    ctx["job_try"] = 2
    assert await evaluate_application(ctx, *args) == {"status": "completed"}
    assert await evaluate_application(ctx, *args) == {"status": "already_completed"}
    ctx["ai"].evaluate.assert_awaited_once()
    ctx["resumes"].extract.assert_called_once()
    assert ctx["adapter"].save_candidate_evaluation.await_count == 2


async def test_missing_evaluation_endpoint_retains_output_and_operator_retry_recovers(durable_context):
    ctx = durable_context
    application_id = (await submit(ctx))["application_id"]
    arq_key = "arq:job:evaluation:" + application_id
    await ctx["redis"].delete(arq_key)
    await ctx["redis"].zrem("arq:queue", "evaluation:" + application_id)
    ctx["adapter"].save_candidate_evaluation.side_effect = ConfigurationError("Save endpoint is not configured")
    args = (
        application_id,
        "azure:" + "a" * 32 + ".pdf",
        "resume.pdf",
        ctx["job"].requirement_id,
        ctx["job"].model_dump(),
    )
    assert await evaluate_application(ctx, *args) == {"status": "failed"}
    state_key = f"{ctx['settings'].redis_prefix}:evaluation:{application_id}"
    assert json.loads(await ctx["redis"].get(state_key))["evaluation"]["score"] == 88
    assert "queued" in await retry(application_id, ctx["settings"])
    ctx["adapter"].save_candidate_evaluation.side_effect = None
    assert await evaluate_application(ctx, *args) == {"status": "completed"}
    assert "Already completed" in await retry(application_id, ctx["settings"])
    ctx["ai"].evaluate.assert_awaited_once()


async def test_opaque_redis_sessions_rotation_prevents_stale_session_resurrection(durable_context):
    ctx = durable_context
    store = SessionStore(ctx["settings"], ctx["redis"])
    await store.put("old-sid", {"user": {"sub": "test-sub"}})
    assert await store.put("new-sid", {"csrf_token": "csrf"}, old_sid="old-sid")
    assert not await store.put("old-sid", {"user": {"sub": "test-sub"}}, old_sid="old-sid")
    assert await store.get("old-sid") is None
    assert await store.get("new-sid") == {"csrf_token": "csrf"}
