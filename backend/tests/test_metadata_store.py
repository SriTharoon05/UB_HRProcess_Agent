"""Shared storage contract and optional live PostgreSQL integration checks.

POSTGRES_TEST_URL must identify a dedicated local database ending in _test.
Tests delete the talentmatch schema in that database between cases.
"""

import asyncio
import copy
import hashlib
import os
import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.errors import ConfigurationError, IntegrationError
from app.metadata import MetadataStore, SQLiteMetadata, metadata_store
from app.migrate_metadata import migrate, read_source
from app.postgres_metadata import PostgresMetadata


def record(application_id="APP-1", *, company="DAT", owner="person", requirement="REQ0013", fingerprint="same-input"):
    payload = {"owner_issuer": "linkedin", "owner_sub": owner, "application_id": application_id,
               "resume_sha256": "a" * 64, "consent_version": "v1", "candidate_name": "Applicant 姓名"}
    return {"application_id": application_id, "company": company, "requirement_id": requirement,
            "payload": payload, "fingerprint": fingerprint, "payload_sha256": "b" * 64,
            "job_snapshot": {"requirement_id": requirement, "title": "Engineer"}, "stage": "ready"}


def configured_postgres_settings():
    url = os.environ.get("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL not configured for dedicated local integration database")
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or not parsed.path.endswith("_test"):
        pytest.fail("POSTGRES_TEST_URL must be a dedicated localhost database ending in _test")
    return Settings(_env_file=None, metadata_backend="postgres", database_url=url, database_sslmode="disable")


@pytest.fixture
def postgres_settings():
    return configured_postgres_settings()


@pytest.fixture
async def postgres(postgres_settings):
    store = PostgresMetadata(postgres_settings)
    with store.connection() as connection:
        connection.execute("DROP SCHEMA IF EXISTS talentmatch CASCADE")
    await store.initialize()
    yield store
    with store.connection() as connection:
        connection.execute("DROP SCHEMA IF EXISTS talentmatch CASCADE")


@pytest.fixture(params=["sqlite", "postgres"])
async def store(request, tmp_path):
    if request.param == "postgres":
        result = PostgresMetadata(configured_postgres_settings())
        with result.connection() as connection:
            connection.execute("DROP SCHEMA IF EXISTS talentmatch CASCADE")
    else:
        result = SQLiteMetadata(tmp_path / "metadata.sqlite3")
    await result.initialize()
    yield result
    if request.param == "postgres":
        with result.connection() as connection:
            connection.execute("DROP SCHEMA IF EXISTS talentmatch CASCADE")


async def test_shared_store_contract_persists_full_snapshots_and_scopes_reads(store):
    assert isinstance(store, MetadataStore)
    value = record()
    saved, created = await store.reserve("submission-1", value)
    assert created and saved == value
    await store.reserve("submission-2", record("APP-2", company="OTHER", owner="other"))
    await store.reserve("submission-3", record("APP-3", requirement="REQ0014"))
    assert await store.get_submission("submission-1") == value
    assert await store.get_application("APP-1", "DAT") == value
    assert await store.get_application("APP-1", "OTHER") is None
    assert await store.get_submission("absent") is None
    assert len(await store.submissions(company="DAT")) == 2
    assert len(await store.submissions(company="DAT", owner=("linkedin", "person"), requirement_id="REQ0013")) == 1
    state = {"status": "Processing", "evaluation": {"summary": "Evidence résumé", "score": 71}}
    await store.save_evaluation_state("APP-1", state)
    assert await store.get_evaluation_state("APP-1") == state
    state.update(status="Completed", evaluation_confirmed=True)
    await store.save_evaluation_state("APP-1", state)
    assert await store.get_evaluation_state("APP-1") == state


async def test_concurrent_reservation_freezes_one_payload_and_conflicts_are_safe(store):
    results = await asyncio.gather(*(store.reserve("one-key", record(f"APP-{index}")) for index in range(8)))
    assert sum(created for _, created in results) == 1
    assert len({row["application_id"] for row, _ in results}) == 1
    with pytest.raises(HTTPException) as failure:
        await store.reserve("one-key", record("different-id", fingerprint="different-resume"))
    assert failure.value.status_code == 409
    assert len(await store.submissions()) == 1


async def test_frozen_metadata_and_candidate_acknowledgement_cannot_change(store):
    original = record()
    await store.reserve("key", original)
    changed = copy.deepcopy(original)
    changed["payload"]["candidate_name"] = "Altered"
    with pytest.raises(IntegrationError, match="Frozen application metadata"):
        await store.update_submission("key", changed)
    accepted = {**original, "stage": "accepted", "candidate_id": "CAN-1"}
    await store.update_submission("key", accepted)
    with pytest.raises(IntegrationError, match="CandidateId"):
        await store.update_submission("key", {**accepted, "candidate_id": "CAN-2"})
    assert await store.get_submission("key") == accepted


async def test_postgres_separate_instances_share_state_and_lock(postgres, postgres_settings):
    other = PostgresMetadata(postgres_settings)
    await postgres.reserve("key", record())
    assert await other.get_application("APP-1") == record()
    async with postgres.evaluation_lock("APP-1") as acquired:
        assert acquired
        async with other.evaluation_lock("APP-1") as second:
            assert not second
        async with other.evaluation_lock("APP-2") as different:
            assert different
    async with other.evaluation_lock("APP-1") as released:
        assert released


async def test_postgres_global_lock_releases_after_cancellation(postgres, postgres_settings):
    acquired_event = asyncio.Event()

    async def running():
        async with postgres.evaluation_lock("APP-1") as acquired:
            assert acquired
            acquired_event.set()
            await asyncio.Future()
    task = asyncio.create_task(running())
    await acquired_event.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with PostgresMetadata(postgres_settings).evaluation_lock("APP-1") as acquired:
        assert acquired


async def test_postgres_private_schema_rls_and_schema_version(postgres):
    rows = await postgres.run(lambda connection: connection.execute("""
        SELECT relname, relrowsecurity FROM pg_class
        JOIN pg_namespace ON pg_class.relnamespace=pg_namespace.oid
        WHERE nspname='talentmatch' AND relkind='r'
    """).fetchall())
    assert set(rows) == {("applications", True), ("evaluation_states", True), ("schema_version", True)}
    await postgres.run(lambda connection: connection.execute("UPDATE talentmatch.schema_version SET version=999"))
    postgres._initialized = False
    with pytest.raises(IntegrationError, match="schema version"):
        await postgres.initialize()


async def test_postgres_driver_failures_do_not_expose_connection_credentials(caplog):
    secret = "never-log-this-database-password"
    value = PostgresMetadata(Settings(_env_file=None,
        database_url=f"postgresql://user:{secret}@127.0.0.1:1/talentmatch_test",
        database_sslmode="disable", database_connect_timeout=1))
    with pytest.raises(IntegrationError) as failure:
        await value.initialize()
    assert secret not in str(failure.value) and secret not in caplog.text
    assert failure.value.__cause__ is None


@pytest.mark.parametrize("url,sslmode", [
    ("", "verify-full"), ("https://example.test/secret", "verify-full"),
    ("postgresql://user:secret@remote.example/database", "disable"),
    ("postgresql://user:secret@localhost/database?host=remote.example", "disable"),
    ("postgresql://user:secret@localhost/database?hostaddr=203.0.113.1", "disable"),
])
def test_invalid_or_unverified_remote_database_url_is_rejected_safely(url, sslmode):
    with pytest.raises(ConfigurationError) as failure:
        PostgresMetadata(Settings(_env_file=None, database_url=url, database_sslmode=sslmode))
    assert "secret" not in str(failure.value)


def test_verified_tls_and_pooler_compatible_options_default():
    settings = Settings(_env_file=None, metadata_backend="postgres",
                        database_url="postgresql://user:private@pooler.example:6543/postgres")
    store = metadata_store(settings)
    assert isinstance(store, PostgresMetadata)
    assert store._options["sslmode"] == "verify-full"
    assert store._options["sslrootcert"] == "system"
    assert store._options["prepare_threshold"] is None
    assert "private" not in repr(settings)
    assert isinstance(metadata_store(Settings(_env_file=None)), SQLiteMetadata)


@pytest.mark.parametrize("blank", ["", "   "])
def test_dotenv_optional_certificate_blank_uses_system_trust(tmp_path, blank):
    env = tmp_path / ".env"
    env.write_text("DATABASE_SSLROOTCERT=" + blank + "\n")
    settings = Settings(_env_file=env, database_url="postgresql://user:private@pooler.example/postgres")
    assert settings.database_sslrootcert is None
    assert PostgresMetadata(settings)._options["sslrootcert"] == "system"


async def source_database(tmp_path, *, two=False):
    source = SQLiteMetadata(tmp_path / "source.sqlite3")
    await source.reserve("one", record())
    await source.save_evaluation_state("APP-1", {"status": "Failed", "evaluation": {"score": 73}})
    if two:
        await source.reserve("two", record("APP-2"))
    return source


async def test_migration_preserves_source_and_json_and_is_idempotent(postgres, postgres_settings, tmp_path):
    source = await source_database(tmp_path)
    before = hashlib.sha256(source.path.read_bytes()).digest()
    result = await migrate(source.path, postgres_settings)
    assert result == {"applications": 1, "evaluation_states": 1, "dry_run": False,
                      "inserted_applications": 1, "inserted_evaluation_states": 1}
    assert await postgres.get_application("APP-1") == await source.get_application("APP-1")
    assert await postgres.get_evaluation_state("APP-1") == await source.get_evaluation_state("APP-1")
    repeated = await migrate(source.path, postgres_settings)
    assert repeated["inserted_applications"] == repeated["inserted_evaluation_states"] == 0
    assert hashlib.sha256(source.path.read_bytes()).digest() == before


async def test_migration_conflict_rolls_back_all_prior_insertions(postgres, postgres_settings, tmp_path):
    source = await source_database(tmp_path, two=True)
    conflicting = record("APP-2", fingerprint="different-fingerprint")
    await postgres.reserve("two", conflicting)
    with pytest.raises(IntegrationError, match="conflicts"):
        await migrate(source.path, postgres_settings)
    assert await postgres.get_application("APP-1") is None
    assert await postgres.get_evaluation_state("APP-1") is None
    assert await postgres.get_application("APP-2") == conflicting


async def test_migration_evaluation_conflict_rolls_back_application_inserts(postgres, postgres_settings, tmp_path):
    source = await source_database(tmp_path, two=True)
    await postgres.reserve("one", record())
    await postgres.save_evaluation_state("APP-1", {"status": "Completed"})
    with pytest.raises(IntegrationError, match="evaluation metadata"):
        await migrate(source.path, postgres_settings)
    assert await postgres.get_application("APP-2") is None
    assert await postgres.get_evaluation_state("APP-1") == {"status": "Completed"}


async def test_migration_dry_run_never_connects_to_target_or_modifies_source(tmp_path):
    source = await source_database(tmp_path)
    before = source.path.read_bytes()
    settings = Settings(_env_file=None, database_url="")
    result = await migrate(source.path, settings, dry_run=True)
    assert result["applications"] == result["evaluation_states"] == 1
    assert result["inserted_applications"] == 0 and result["dry_run"] is True
    assert source.path.read_bytes() == before


def test_migration_missing_or_invalid_source_is_not_created(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(IntegrationError, match="does not exist"):
        read_source(missing)
    assert not missing.exists()
    malformed = tmp_path / "malformed.sqlite3"
    malformed.write_bytes(b"not a database")
    with pytest.raises(IntegrationError, match="invalid"):
        read_source(malformed)


async def test_migration_rejects_source_identity_mismatch(tmp_path):
    source = await source_database(tmp_path)
    with sqlite3.connect(source.path) as connection:
        connection.execute("UPDATE applications SET owner_sub='different'")
    with pytest.raises(IntegrationError, match="inconsistent"):
        read_source(source.path)
