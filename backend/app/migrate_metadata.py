"""Atomically copy portal metadata from read-only SQLite to PostgreSQL.

Stop every API and worker connected to the source before migration. Private
resume files are not database rows: retain Azure Blob access, or transfer the
local resume volume separately. Redis queues/sessions are recreated, not copied.

    python -m app.migrate_metadata --source .local/talentmatch.sqlite3 --dry-run
    python -m app.migrate_metadata --source .local/talentmatch.sqlite3

DATABASE_URL and TLS options come from backend .env. Identical reruns are safe;
any conflicting row aborts the complete target data import without overwriting.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from app.config import get_settings
from app.errors import IntegrationError
from app.metadata import encode
from app.observability import configure_logging, error_fields, log_event
from app.postgres_metadata import PostgresMetadata


def read_source(source: Path | str) -> tuple[list[tuple], list[tuple]]:
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise IntegrationError("SQLite migration source does not exist", retryable=False)
    try:
        # mode=ro cannot create or modify source rows/schema. One read snapshot
        # includes committed WAL data and keeps applications/states consistent.
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise IntegrationError("SQLite migration source schema version is unsupported", retryable=False)
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise IntegrationError("SQLite migration source failed integrity validation", retryable=False)
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise IntegrationError("SQLite migration source contains orphaned evaluations", retryable=False)
            applications = connection.execute("""
                SELECT application_id, submission_key, company, requirement_id,
                       owner_issuer, owner_sub, fingerprint, record_json
                FROM applications ORDER BY application_id
            """).fetchall()
            states = connection.execute("SELECT application_id, state_json FROM evaluation_states ORDER BY application_id").fetchall()
        for row in applications:
            record = json.loads(row[7])
            expected = (record["application_id"], record["company"], record["requirement_id"],
                        record["payload"]["owner_issuer"], record["payload"]["owner_sub"], record["fingerprint"])
            if (row[0], *row[2:7]) != expected:
                raise ValueError
            # Validate fields relied on by immutable-snapshot enforcement.
            for field in ("payload_sha256", "job_snapshot", "stage"):
                if field not in record:
                    raise ValueError
        for _, value in states:
            if not isinstance(json.loads(value), dict):
                raise ValueError
        return applications, states
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        raise IntegrationError("SQLite migration source is invalid or inconsistent", retryable=False) from None


async def migrate(source: Path | str, settings=None, *, dry_run=False) -> dict[str, int | bool]:
    applications, states = await asyncio.to_thread(read_source, source)
    result = {"applications": len(applications), "evaluation_states": len(states), "dry_run": dry_run,
              "inserted_applications": 0, "inserted_evaluation_states": 0}
    if dry_run:
        # Source-only validation intentionally neither opens nor changes target.
        log_event("metadata.migration", "validated", count=len(applications), entries_count=len(states),
                  storage="sqlite")
        return result
    target = PostgresMetadata(settings or get_settings())
    await target.initialize()

    def perform(connection):
        # All rows and both tables live in this one transaction. A conflict at
        # any point rolls back every insert; do not silently overwrite target.
        connection.execute("LOCK TABLE talentmatch.applications, talentmatch.evaluation_states IN SHARE ROW EXCLUSIVE MODE")
        for row in applications:
            existing = connection.execute("""
                SELECT application_id, submission_key, company, requirement_id,
                       owner_issuer, owner_sub, fingerprint, record_json
                FROM talentmatch.applications WHERE application_id=%s OR submission_key=%s
            """, (row[0], row[1])).fetchall()
            if existing:
                if len(existing) != 1 or existing[0][:7] != row[:7] or json.loads(existing[0][7]) != json.loads(row[7]):
                    raise IntegrationError("Migration conflicts with existing PostgreSQL application metadata; nothing was imported",
                                           retryable=False)
                continue
            canonical = (*row[:7], encode(json.loads(row[7])))
            connection.execute("INSERT INTO talentmatch.applications VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", canonical)
            result["inserted_applications"] += 1
        for application_id, state_json in states:
            existing = connection.execute("SELECT state_json FROM talentmatch.evaluation_states WHERE application_id=%s",
                                          (application_id,)).fetchone()
            if existing:
                if json.loads(existing[0]) != json.loads(state_json):
                    raise IntegrationError("Migration conflicts with existing PostgreSQL evaluation metadata; nothing was imported",
                                           retryable=False)
                continue
            connection.execute("INSERT INTO talentmatch.evaluation_states VALUES(%s,%s)",
                               (application_id, encode(json.loads(state_json))))
            result["inserted_evaluation_states"] += 1
        # Verify within the transaction, including byte-independent JSON equality.
        for row in applications:
            actual = connection.execute("SELECT record_json FROM talentmatch.applications WHERE application_id=%s", (row[0],)).fetchone()
            if not actual or json.loads(actual[0]) != json.loads(row[7]):
                raise IntegrationError("Migration verification failed; nothing was imported", retryable=False)
        for application_id, state_json in states:
            actual = connection.execute("SELECT state_json FROM talentmatch.evaluation_states WHERE application_id=%s", (application_id,)).fetchone()
            if not actual or json.loads(actual[0]) != json.loads(state_json):
                raise IntegrationError("Migration verification failed; nothing was imported", retryable=False)

    await target.run(perform)
    log_event("metadata.migration", "completed", count=len(applications), entries_count=len(states), storage="postgres")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Existing SQLite metadata database")
    parser.add_argument("--dry-run", action="store_true", help="Validate source only; do not connect to PostgreSQL")
    args = parser.parse_args()
    configure_logging()
    try:
        result = asyncio.run(migrate(args.source, dry_run=args.dry_run))
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        # No driver exception text or connection URI may enter operator logs.
        log_event("metadata.migration", "failed", **error_fields(exc))
        if isinstance(exc, IntegrationError):
            print("Migration failed: " + exc.detail, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
