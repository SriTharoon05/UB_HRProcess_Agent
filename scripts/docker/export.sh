#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
assert_docker
target=${1:-"$PACKAGE_ROOT/dist/talentmatch"}
if [ "${2:-}" = --build ]; then sh "$SCRIPT_DIR/build.sh"; fi
mkdir -p "$target"
target=$(CDPATH= cd -- "$target" && pwd)
[ "$target" != "$PACKAGE_ROOT" ] || { echo 'Export to a separate folder.' >&2; exit 1; }
cp "$PACKAGE_ROOT/compose.yml" "$target/compose.yml"
cp "$PACKAGE_ROOT/deploy/docker/.env.example" "$target/.env.example"
for name in common.ps1 setup.ps1 setup.cmd start.ps1 start.cmd stop.ps1 stop.cmd common.sh setup.sh start.sh stop.sh; do cp "$SCRIPT_DIR/$name" "$target/$name"; done
if [ -d "$PACKAGE_ROOT/docs" ]; then
    mkdir -p "$target/docs"
    cp -R "$PACKAGE_ROOT/docs/." "$target/docs/"
fi
cat > "$target/Docker instructions.md" <<'GUIDE'
# TalentMatch portable runtime

Start with [Docker setup and transfer instructions](docs/docker-local.md).

- [Supabase migration and environment settings](docs/supabase.md)
- [Technical reference (Word)](docs/reference/TalentMatch_AI_Technical_Reference.docx)
- [Business reference (Word)](docs/reference/TalentMatch_AI_Business_Reference.docx)

Put your private .env beside compose.yml. Run setup.cmd once on Windows or ./setup.sh on Linux/macOS.
After initial setup, use Docker Desktop > Containers > talentmatch > Play.
Open https://localhost:7242. The LinkedIn callback is https://localhost:7242/auth/linkedin/callback.
GUIDE
docker save --output "$target/images.tar" talentmatch-backend:phase1 talentmatch-web:phase1 redis:7.4-alpine
if command -v sha256sum >/dev/null 2>&1; then sha256sum "$target/images.tar" | cut -d ' ' -f1 > "$target/images.sha256"; else shasum -a 256 "$target/images.tar" | cut -d ' ' -f1 > "$target/images.sha256"; fi
docker image inspect talentmatch-backend:phase1 --format '{{.Os}}/{{.Architecture}}' > "$target/image-platform.txt"
echo "Exported source-free package: $target"
echo 'Transfer the folder plus a separately secured .env. No source, certificates, database, resumes or secrets were exported.'
echo 'Check image-platform.txt; the recipient needs compatible Linux containers in Docker Desktop.'
