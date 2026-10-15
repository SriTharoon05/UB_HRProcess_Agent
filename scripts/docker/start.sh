#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
assert_docker
initialize_env
cd "$PACKAGE_ROOT"
[ -f .certs/server/localhost-key.pem ] || { echo 'Run setup.sh once to create localhost certificates.' >&2; exit 1; }
docker compose --env-file .env -f compose.yml up -d --wait --wait-timeout 180 --no-build --pull never
echo 'TalentMatch is ready at https://localhost:7242'
echo 'LinkedIn callback: https://localhost:7242/auth/linkedin/callback'
echo 'Next time: Docker Desktop > Containers > talentmatch > Start (group Play).'
echo 'After editing .env, rerun start.sh to recreate with updated settings.'
