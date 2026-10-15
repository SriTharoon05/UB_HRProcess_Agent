"""Azure image preflight and internal readiness; never emit configuration values."""

import asyncio
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, "/app")


def preflight():
    from app.config import get_settings
    from app.errors import ConfigurationError
    from app.observability import log_event

    settings = get_settings()
    if settings.app_env == "production":
        if settings.metadata_backend != "postgres" or not settings.database_url:
            raise ConfigurationError("Azure production requires PostgreSQL metadata. Set METADATA_BACKEND=postgres and DATABASE_URL.")
        origin = settings.frontend_url.rstrip("/")
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or parsed.port not in {None, 443}
                or parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ConfigurationError("Azure production requires the public HTTPS origin without a path or localhost port.")
        if settings.backend_url.rstrip("/") != origin or settings.cors_origins != [origin]:
            raise ConfigurationError("Frontend, backend and CORS must use the same public HTTPS origin.")
        if settings.linkedin_redirect_uri != origin + "/auth/linkedin/callback":
            raise ConfigurationError("LINKEDIN_REDIRECT_URI must match the public HTTPS origin and /auth/linkedin/callback.")
        if not settings.hr_username or not settings.hr_password:
            raise ConfigurationError("Set HR_USERNAME and HR_PASSWORD in App Service settings or Key Vault references.")
        if settings.database_sslmode != "verify-full":
            raise ConfigurationError("Azure production requires DATABASE_SSLMODE=verify-full.")
    for directory in ("redis", "client", "proxy", "fastcgi", "uwsgi", "scgi", "resumes"):
        (Path("/tmp/talentmatch") / directory).mkdir(parents=True, exist_ok=True)
    log_event("azure.preflight", "completed", mode=settings.app_env)


def ready():
    from app.config import get_settings
    from redis.asyncio import Redis

    settings = get_settings()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/api/health", timeout=2) as response:
        if response.status != 200:
            return False

    async def queue_ready():
        client = Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        try:
            return bool(await client.ping()) and (settings.demo_mode or bool(
                await client.exists(settings.redis_prefix + ":worker:health")))
        finally:
            await client.aclose()
    return asyncio.run(queue_ready())


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/healthz":
            self.send_error(404)
            return
        try:
            healthy = ready()
        except Exception:
            healthy = False
        payload = json.dumps({"status": "ok" if healthy else "unavailable",
                              "revision": os.environ.get("BUILD_REVISION", "development")}).encode()
        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "preflight":
        preflight()
    elif action == "serve-health":
        ThreadingHTTPServer(("127.0.0.1", 8010), HealthHandler).serve_forever()
    elif action == "health":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8080/healthz", timeout=6) as response:
            return 0 if response.status == 200 else 1
    else:
        raise SystemExit("Supported commands: preflight, serve-health, health")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Provider/Redis/DB exception messages can contain credentials.
        print("Azure runtime failed: " + type(exc).__name__, file=sys.stderr)
        from app.errors import ConfigurationError
        if isinstance(exc, ConfigurationError):
            print(exc.detail, file=sys.stderr)
        raise SystemExit(1) from None
