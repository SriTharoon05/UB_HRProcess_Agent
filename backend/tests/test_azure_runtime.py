"""Deployment preflight must fail safely before any Azure child is started."""

import importlib.util
import io
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.errors import ConfigurationError

spec = importlib.util.spec_from_file_location(
    "azure_runtime", Path(__file__).resolve().parents[2] / "deploy/azure/runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def production(**changes):
    options = dict(_env_file=None, app_env="production", demo_mode=False,
                   frontend_url="https://portal.example.test", backend_url="https://portal.example.test",
                   cors_origins=["https://portal.example.test"],
                   linkedin_redirect_uri="https://portal.example.test/auth/linkedin/callback",
                   metadata_backend="postgres", database_url="postgresql://user:private-password@db.example.test/postgres",
                   hr_username="test-hr", hr_password="test-only")
    options.update(changes)
    return Settings(**options)


def test_public_production_origin_and_postgres_are_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.get_settings", lambda: production())
    monkeypatch.setattr(runtime, "Path", lambda _: tmp_path)
    runtime.preflight()
    assert (tmp_path / "redis").is_dir()


@pytest.mark.parametrize("changes,message", [
    ({"metadata_backend": "sqlite"}, "requires PostgreSQL"),
    ({"database_url": ""}, "requires PostgreSQL"),
    ({"frontend_url": "https://localhost:7242"}, "public HTTPS origin"),
    ({"frontend_url": "https://portal.example.test/path"}, "public HTTPS origin"),
    ({"frontend_url": "https://portal.example.test:7242"}, "public HTTPS origin"),
    ({"backend_url": "https://other.example.test"}, "same public HTTPS origin"),
    ({"cors_origins": ["https://other.example.test"]}, "same public HTTPS origin"),
    ({"linkedin_redirect_uri": "https://portal.example.test/wrong"}, "LINKEDIN_REDIRECT_URI"),
    ({"hr_password": ""}, "HR_USERNAME and HR_PASSWORD"),
    ({"database_sslmode": "disable"}, "verify-full"),
    ({"database_sslmode": "require"}, "verify-full"),
])
def test_unsafe_or_incomplete_hosted_configuration_is_rejected_without_values(monkeypatch, changes, message):
    monkeypatch.setattr("app.config.get_settings", lambda: production(**changes))
    with pytest.raises(ConfigurationError, match=message) as caught:
        runtime.preflight()
    assert "private-password" not in str(caught.value)


def test_explicit_local_demo_remains_supported_for_container_smoke(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(runtime, "Path", lambda _: tmp_path)
    runtime.preflight()


def test_readiness_returns_503_without_leaking_a_failed_dependency(monkeypatch):
    def unavailable():
        raise OSError("private-provider-message")
    monkeypatch.setattr(runtime, "ready", unavailable)
    handler = object.__new__(runtime.HealthHandler)
    handler.path = "/healthz"
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.wfile = io.BytesIO()
    handler.do_GET()
    handler.send_response.assert_called_once_with(503)
    assert b'"status": "unavailable"' in handler.wfile.getvalue()
    assert b"private-provider-message" not in handler.wfile.getvalue()
