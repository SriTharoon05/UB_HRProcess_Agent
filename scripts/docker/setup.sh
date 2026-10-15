#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
assert_docker
initialize_env
cd "$PACKAGE_ROOT"
if [ -f images.tar ]; then
    [ -f images.sha256 ] || { echo 'Missing images.sha256; obtain the complete package.' >&2; exit 1; }
    expected=$(tr -d '\r\n' < images.sha256)
    if command -v sha256sum >/dev/null 2>&1; then actual=$(sha256sum images.tar | cut -d ' ' -f1); else actual=$(shasum -a 256 images.tar | cut -d ' ' -f1); fi
    [ "$expected" = "$actual" ] || { echo 'Image checksum mismatch. Transfer the package again.' >&2; exit 1; }
    docker load --input images.tar
fi
for image in talentmatch-backend:phase1 talentmatch-web:phase1 redis:7.4-alpine; do docker image inspect "$image" --format '{{.RepoTags}}'; done
mkdir -p .certs
chmod 700 .certs
if [ ! -f .certs/server/localhost-key.pem ]; then
    docker run --rm --pull never --user 0:0 --mount "type=bind,src=$PACKAGE_ROOT/.certs,dst=/certs" talentmatch-backend:phase1 python /app/docker/certificates.py /certs
fi
if [ "${1:-}" = '--skip-trust' ]; then
    echo 'Trust skipped. Import .certs/rootCA.pem into your browser/system trusted roots before LinkedIn sign-in.'
elif [ "$(uname -s)" = Darwin ]; then
    security add-trusted-cert -r trustRoot -k "$HOME/Library/Keychains/login.keychain-db" .certs/rootCA.pem
elif [ -d /usr/local/share/ca-certificates ] && command -v update-ca-certificates >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ]; then
        cp .certs/rootCA.pem /usr/local/share/ca-certificates/talentmatch-local.crt
        update-ca-certificates
    else
        sudo cp .certs/rootCA.pem /usr/local/share/ca-certificates/talentmatch-local.crt
        sudo update-ca-certificates
    fi
else
    echo 'Import .certs/rootCA.pem manually into your OS/browser trusted roots; see Docker instructions.'
fi
sh "$SCRIPT_DIR/start.sh"
