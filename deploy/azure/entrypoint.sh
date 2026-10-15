#!/bin/sh
set -eu
cd /app
python /app/azure/runtime.py preflight
echo 'Starting Redis, FastAPI, ARQ worker, Nginx and readiness via Supervisor.'
exec /usr/bin/supervisord -c /app/azure/supervisord.conf
