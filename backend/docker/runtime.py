"""Small image-only runtime commands. No credentials or provider bodies are printed."""

import asyncio
import logging
import signal
import sys
import threading
import urllib.request

sys.path.insert(0, "/app")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "api-health":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8000/api/health", timeout=4) as response:
            return 0 if response.status == 200 else 1

    from app.config import get_settings
    settings = get_settings()
    if action == "worker-health":
        if settings.demo_mode:
            return 0
        from redis.asyncio import Redis

        async def healthy():
            client = Redis.from_url(settings.redis_url)
            try:
                return bool(await client.exists(settings.redis_prefix + ":worker:health"))
            finally:
                await client.aclose()
        return 0 if asyncio.run(healthy()) else 1
    if action == "worker":
        from app.observability import error_fields, log_event
        if settings.demo_mode:
            # Demo evaluations are fixtures. Keep the Compose group healthy
            # without consuming or modifying a connected queue.
            done = threading.Event()
            signal.signal(signal.SIGTERM, lambda *_: done.set())
            signal.signal(signal.SIGINT, lambda *_: done.set())
            log_event("worker.process", "idle", reason="explicit_demo_mode")
            done.wait()
            return 0
        from app.worker import WorkerSettings, configure_worker_logging, run_worker
        configure_worker_logging(settings)
        WorkerSettings.health_check_interval = 30
        WorkerSettings.health_check_key = settings.redis_prefix + ":worker:health"
        try:
            run_worker(WorkerSettings)
        except Exception as exc:
            log_event("worker.process", "failed", level=logging.ERROR, **error_fields(exc))
            return 1
        return 0
    raise SystemExit("Supported commands: api-health, worker, worker-health")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Health failures must not leak a Redis URL/password in tracebacks.
        print("Runtime command failed: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
