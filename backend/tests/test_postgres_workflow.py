"""Live PostgreSQL through the real coordinator/worker/lean D365 adapter.

External D365 and AI calls use controlled transports; database operations are
real and require the dedicated POSTGRES_TEST_URL from test_metadata_store.
"""

import pytest
from arq import Retry

from app.errors import IntegrationError
from app.queue import SubmissionCoordinator
from app.worker import evaluate_application
import test_metadata_store as metadata_tests
import test_sqlite_d365 as workflow_tests

postgres = metadata_tests.postgres
postgres_settings = metadata_tests.postgres_settings
workflow_context = workflow_tests.context
submit = workflow_tests.submit


async def test_postgres_submission_worker_confirmation_and_history(postgres, workflow_context):
    ctx = workflow_context
    ctx["adapter"].metadata = postgres
    ctx["coordinator"] = SubmissionCoordinator(ctx["settings"], ctx["adapter"], ctx["resumes"], ctx["redis"])
    application_id = (await submit(ctx))["application_id"]
    assert (await postgres.get_application(application_id))["stage"] == "queued"
    args = ctx["redis"].jobs["arq:job:evaluation:" + application_id]
    assert await evaluate_application(ctx, *args) == {"status": "completed"}
    retained = await postgres.get_evaluation_state(application_id)
    assert retained["status"] == "Completed" and retained["evaluation_confirmed"] is True
    assert retained["evaluation_id"].startswith("EVA-")
    history = await ctx["adapter"].get_my_applications(ctx["user"])
    assert len(history) == 1 and history[0].evaluation.score == 88
    assert ctx["calls"][-1][0] == "/save"
    assert ctx["calls"][-1][1]["_request"]["EvaluationId"] == retained["evaluation_id"]
    assert await evaluate_application(ctx, *args) == {"status": "already_completed"}
    ctx["ai"].evaluate.assert_awaited_once()


async def test_postgres_failed_d365_save_reuses_cached_ai_and_stable_id(postgres, workflow_context, monkeypatch):
    ctx = workflow_context
    ctx["adapter"].metadata = postgres
    ctx["coordinator"] = SubmissionCoordinator(ctx["settings"], ctx["adapter"], ctx["resumes"], ctx["redis"])
    application_id = (await submit(ctx))["application_id"]
    args = ctx["redis"].jobs["arq:job:evaluation:" + application_id]
    original = ctx["adapter"].call_d365_service
    evaluation_ids = []

    async def fail_once(operation, payload=None):
        if operation == "save_candidate_evaluation":
            evaluation_ids.append(payload["evaluation_id"])
            if len(evaluation_ids) == 1:
                raise IntegrationError("Temporary write failure")
        return await original(operation, payload)
    monkeypatch.setattr(ctx["adapter"], "call_d365_service", fail_once)
    with pytest.raises(Retry):
        await evaluate_application(ctx, *args)
    retained = await postgres.get_evaluation_state(application_id)
    assert retained["status"] == "Retrying" and retained["evaluation_confirmed"] is False
    assert (await ctx["adapter"].get_application(application_id)).evaluation is None
    ctx["redis"].values.clear()
    ctx["job_try"] = 2
    assert await evaluate_application(ctx, *args) == {"status": "completed"}
    assert len(evaluation_ids) == 2 and evaluation_ids[0] == evaluation_ids[1]
    assert (await ctx["adapter"].get_application(application_id)).evaluation.score == 88
    ctx["ai"].evaluate.assert_awaited_once()
