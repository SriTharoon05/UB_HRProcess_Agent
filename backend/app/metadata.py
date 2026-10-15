"""Durable portal metadata and submission outbox, shared by API and worker.

F&O stores business rows. SQLite stores immutable application snapshots, private
resume references, consent, processing state and full AI provenance. Redis is a
queue/session transport, never the only copy of these records.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Protocol, runtime_checkable

from fastapi import HTTPException

from app.errors import IntegrationError
from app.observability import log_event, traced


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@runtime_checkable
class MetadataStore(Protocol):
    """Durable portal state; transport/session locks remain separate."""

    storage_name: str

    async def initialize(self): ...
    async def reserve(self, key: str, record: dict) -> tuple[dict, bool]: ...
    async def get_submission(self, key: str) -> dict | None: ...
    async def get_application(self, application_id: str, company: str | None = None) -> dict | None: ...
    async def update_submission(self, key: str, record: dict): ...
    async def submissions(self, *, company=None, owner=None, requirement_id=None): ...
    async def get_evaluation_state(self, application_id: str): ...
    async def save_evaluation_state(self, application_id: str, state: dict): ...
    def evaluation_lock(self, application_id: str): ...


def metadata_store(settings) -> MetadataStore:
    if settings.metadata_backend == "postgres":
        from app.postgres_metadata import PostgresMetadata
        return PostgresMetadata(settings)
    return SQLiteMetadata(settings.sqlite_database_path)


class SQLiteMetadata:
    storage_name = "sqlite"

    @asynccontextmanager
    async def evaluation_lock(self, application_id: str):
        # One SQLite deployment already uses a shared Redis lock. PostgreSQL
        # provides an additional cross-deployment lock for shared cloud records.
        yield True

    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser().resolve()
        self._initialized = False

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @traced("sqlite.initialize")
    def _initialize(self):
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise IntegrationError("SQLite metadata schema version is unsupported", retryable=False)
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS applications (
                    application_id TEXT PRIMARY KEY,
                    submission_key TEXT NOT NULL UNIQUE,
                    company TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    owner_issuer TEXT NOT NULL,
                    owner_sub TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS applications_owner
                    ON applications(company, owner_issuer, owner_sub);
                CREATE INDEX IF NOT EXISTS applications_requirement
                    ON applications(company, requirement_id);
                CREATE TABLE IF NOT EXISTS evaluation_states (
                    application_id TEXT PRIMARY KEY REFERENCES applications(application_id),
                    state_json TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)
        self._initialized = True
        log_event("sqlite.schema", "validated", schema_version=1, storage="sqlite")

    async def initialize(self):
        if not self._initialized:
            await asyncio.to_thread(self._initialize)

    @traced("sqlite.transaction")
    async def run(self, callback):
        await self.initialize()

        def perform():
            with self.connection() as connection:
                return callback(connection)

        return await asyncio.to_thread(perform)

    @traced("sqlite.submission.reserve")
    async def reserve(self, key: str, record: dict) -> tuple[dict, bool]:
        """Freeze one ApplicationId/payload per stable caller submission key."""
        def perform(connection):
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT record_json FROM applications WHERE submission_key=?", (key,)
            ).fetchone()
            if existing:
                old = json.loads(existing[0])
                if old["fingerprint"] != record["fingerprint"]:
                    raise HTTPException(409, "Idempotency-Key was already used for a different application")
                return old, False
            payload = record["payload"]
            connection.execute(
                "INSERT INTO applications VALUES(?,?,?,?,?,?,?,?)",
                (record["application_id"], key, record["company"], record["requirement_id"],
                 payload["owner_issuer"], payload["owner_sub"], record["fingerprint"], encode(record)),
            )
            return record, True

        return await self.run(perform)

    async def get_submission(self, key: str) -> dict | None:
        return await self._one("SELECT record_json FROM applications WHERE submission_key=?", (key,))

    async def get_application(self, application_id: str, company: str | None = None) -> dict | None:
        if company is not None:
            return await self._one(
                "SELECT record_json FROM applications WHERE application_id=? AND company=?", (application_id, company)
            )
        return await self._one("SELECT record_json FROM applications WHERE application_id=?", (application_id,))

    @traced("sqlite.read")
    async def _one(self, query, parameters):
        def perform(connection):
            row = connection.execute(query, parameters).fetchone()
            return json.loads(row[0]) if row else None
        return await self.run(perform)

    @traced("sqlite.submission.update")
    async def update_submission(self, key: str, record: dict):
        def perform(connection):
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT record_json FROM applications WHERE submission_key=?", (key,)).fetchone()
            if not row:
                raise IntegrationError("SQLite submission metadata is missing", retryable=False)
            old = json.loads(row[0])
            # Never silently mutate a frozen input or bind new bytes to an old F&O acknowledgement.
            for field in ("application_id", "fingerprint", "payload", "payload_sha256", "company", "requirement_id", "job_snapshot"):
                if old[field] != record[field]:
                    raise IntegrationError("Frozen application metadata cannot be changed", retryable=False)
            if old.get("candidate_id") and old["candidate_id"] != record.get("candidate_id"):
                raise IntegrationError("D365 acknowledgement changed the CandidateId", retryable=False)
            connection.execute("UPDATE applications SET record_json=? WHERE submission_key=?", (encode(record), key))
        await self.run(perform)

    @traced("sqlite.submissions.list")
    async def submissions(self, *, company: str | None = None, owner: tuple[str, str] | None = None,
                          requirement_id: str | None = None):
        clauses, parameters = [], []
        if company is not None:
            clauses.append("company=?")
            parameters.append(company)
        if owner is not None:
            clauses.extend(["owner_issuer=?", "owner_sub=?"])
            parameters.extend(owner)
        if requirement_id is not None:
            clauses.append("requirement_id=?")
            parameters.append(requirement_id)
        query = "SELECT submission_key, record_json FROM applications"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        def perform(connection):
            return [(row[0], json.loads(row[1])) for row in connection.execute(query, parameters)]
        return await self.run(perform)

    @traced("sqlite.evaluation.read")
    async def get_evaluation_state(self, application_id: str):
        return await self._one("SELECT state_json FROM evaluation_states WHERE application_id=?", (application_id,))

    @traced("sqlite.evaluation.save")
    async def save_evaluation_state(self, application_id: str, state: dict):
        def perform(connection):
            connection.execute(
                "INSERT INTO evaluation_states VALUES(?,?) ON CONFLICT(application_id) "
                "DO UPDATE SET state_json=excluded.state_json", (application_id, encode(state)),
            )
        await self.run(perform)
