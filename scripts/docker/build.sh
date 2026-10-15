#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
assert_docker
if [ "$#" -gt 0 ]; then
    docker build --secret "id=build_ca_bundle,src=$1" -t talentmatch-backend:phase1 "$PACKAGE_ROOT/backend"
    docker build --secret "id=build_ca_bundle,src=$1" -t talentmatch-web:phase1 "$PACKAGE_ROOT/frontend"
else
    docker build -t talentmatch-backend:phase1 "$PACKAGE_ROOT/backend"
    docker build -t talentmatch-web:phase1 "$PACKAGE_ROOT/frontend"
fi
docker pull redis:7.4-alpine
