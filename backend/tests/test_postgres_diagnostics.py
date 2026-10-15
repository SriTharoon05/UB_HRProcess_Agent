"""PostgreSQL operator hints distinguish failures without exposing driver text."""

import logging
import sys
from unittest.mock import MagicMock

import psycopg
import pytest

from app import migrate_metadata
from app.config import Settings
from app.errors import IntegrationError
from app.postgres_diagnostics import postgres_failure
from app.postgres_metadata import PostgresMetadata


PRIVATE = "private-password private-host.example private-sql-argument"


def driver_error(message, sqlstate=None):
    exception_type = psycopg.errors.lookup(sqlstate) if sqlstate else psycopg.OperationalError
    return exception_type(message + " " + PRIVATE)


@pytest.mark.parametrize("message,sqlstate,expected,retryable", [
    ("FATAL: Tenant or user not found", None, "tenant_not_found", False),
    ("password authentication failed", None, "invalid_password", False),
    ("FATAL: authentication failure", "28P01", "invalid_password", False),
    ("FATAL: authentication failure", "28000", "authentication_failed", False),
    ("permission denied for schema", "42501", "permission_denied", False),
    ("database does not exist", "3D000", "database_not_found", False),
    ("canceling statement due to statement timeout", "57014", "statement_timeout", True),
    ("canceling statement due to lock timeout", "55P03", "lock_timeout", True),
    ("too many connections", "53300", "connection_limit", True),
    ("configuration limit exceeded", "53400", "connection_limit", True),
    ("MaxClientsInSessionMode", None, "connection_limit", True),
    ("max clients reached", None, "connection_limit", True),
    ("database system is starting up", "57P03", "database_unavailable", True),
    ("Circuit breaker open", None, "database_unavailable", True),
    ("SSL error: certificate verify failed", None, "tls_certificate", False),
    ("self-signed certificate in certificate chain", None, "tls_certificate", False),
    ("could not read root certificate file", None, "tls_certificate", False),
    ("SSL error: wrong version number", None, "tls_negotiation", True),
    ("could not translate host name: getaddrinfo failed", None, "dns_failure", True),
    ("failed to resolve host", None, "dns_failure", True),
    ("connection timeout expired", None, "connection_timeout", True),
    ("connection refused", None, "connection_refused", True),
    ("SSL SYSCALL error: EOF detected", None, "connection_lost", True),
    ("server closed the connection unexpectedly", None, "connection_lost", True),
    ("unfamiliar failure", None, "database_operation_failed", True),
])
def test_postgres_driver_failure_has_fixed_safe_hint(message, sqlstate, expected, retryable):
    reason, detail, is_retryable = postgres_failure(driver_error(message, sqlstate))

    assert reason == expected
    assert isinstance(detail, str) and detail
    assert is_retryable is retryable
    for private in PRIVATE.split():
        assert private not in reason
        assert private not in detail


def test_sqlstate_takes_precedence_over_timeout_word_in_server_error():
    reason, _, retryable = postgres_failure(driver_error("permission denied for timeout column", "42501"))
    assert reason == "permission_denied"
    assert retryable is False


def store():
    return PostgresMetadata(Settings(
        _env_file=None,
        database_url="postgresql://user:private-password@localhost/postgres",
        database_sslmode="require",
    ))


@pytest.mark.parametrize("operation", ["connect", "session_setup", "transaction", "commit"])
def test_metadata_boundary_logs_canonical_hint_without_private_values(monkeypatch, caplog, operation):
    caplog.set_level(logging.INFO, logger="app.workflow")
    connect = MagicMock()
    failure = driver_error("permission denied for schema", "42501")
    if operation == "session_setup":
        connect.return_value.__enter__.return_value.execute.side_effect = failure
    elif operation == "connect":
        connect.side_effect = failure
    elif operation == "commit":
        connect.return_value.__exit__.side_effect = failure
    monkeypatch.setattr(psycopg, "connect", connect)

    with pytest.raises(IntegrationError) as caught:
        with store().connection():
            if operation == "transaction":
                raise failure

    assert caught.value.retryable is False
    event = next(record.workflow_event for record in caplog.records
                 if hasattr(record, "workflow_event") and record.workflow_event["stage"] == "postgres.transaction")
    assert event["reason"] == "permission_denied"
    assert event["hint"]
    assert event["mode"] == "require"
    assert event["operation"] == operation
    assert event["error_code"] == "42501"
    for private in PRIVATE.split():
        assert private not in str(caught.value)
        assert private not in caplog.text


def test_migration_cli_prints_safe_actionable_error(monkeypatch, capsys):
    detail = "PostgreSQL password authentication failed; check the database password in DATABASE_URL."

    async def fail(*args, **kwargs):
        raise IntegrationError(detail, status_code=503, retryable=False) from driver_error("password authentication failed")

    monkeypatch.setattr(migrate_metadata, "migrate", fail)
    monkeypatch.setattr(sys, "argv", ["migrate_metadata", "--source", "backup.sqlite3"])
    with pytest.raises(SystemExit) as caught:
        migrate_metadata.main()

    output = capsys.readouterr()
    assert caught.value.code == 1
    assert detail in output.err
    for private in PRIVATE.split():
        assert private not in output.out + output.err
