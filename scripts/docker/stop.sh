#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
cd "$PACKAGE_ROOT"
docker compose --env-file .env -f compose.yml stop
