#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$SCRIPT_DIR/compose.yml" ]; then PACKAGE_ROOT=$SCRIPT_DIR; else PACKAGE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd); fi
assert_docker() {
    if [ "$(docker info --format '{{.OSType}}')" != linux ]; then
        echo 'Start Docker Desktop with Linux containers and retry.' >&2
        exit 1
    fi
    docker compose version --short
}
initialize_env() {
    if [ -f "$PACKAGE_ROOT/.env" ]; then
        normalized=$(sed -E 's|^(REDIS_URL[[:space:]]*=[[:space:]]*redis://)(localhost|127\.0\.0\.1)(:6379(/[0-9]+)?[[:space:]]*)$|\1redis\3|' "$PACKAGE_ROOT/.env")
        # Keep file contents private; rewrite only a plain host-local Redis URL.
        if ! printf '%s\n' "$normalized" | cmp -s - "$PACKAGE_ROOT/.env"; then
            umask 077
            printf '%s\n' "$normalized" > "$PACKAGE_ROOT/.env"
        fi
        return
    fi
    if [ -f "$PACKAGE_ROOT/backend/.env" ]; then
        umask 077
        sed -E 's|^(REDIS_URL[[:space:]]*=[[:space:]]*redis://)(localhost|127\.0\.0\.1)(:6379(/[0-9]+)?[[:space:]]*)$|\1redis\3|' "$PACKAGE_ROOT/backend/.env" > "$PACKAGE_ROOT/.env"
        echo 'Copied backend/.env to root .env; local Redis points to the Compose redis service. Original file unchanged.'
    else
        umask 077
        example="$PACKAGE_ROOT/.env.example"
        if [ ! -f "$example" ]; then example="$PACKAGE_ROOT/deploy/docker/.env.example"; fi
        cp "$example" "$PACKAGE_ROOT/.env"
        echo 'Created .env. Fill HR, LinkedIn, D365, Azure OpenAI and private Blob settings, then rerun setup. Never commit .env.' >&2
        exit 1
    fi
}
