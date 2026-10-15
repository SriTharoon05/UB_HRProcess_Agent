# Run and transfer the complete local Docker application

The portable deployment runs the web frontend, FastAPI API, evaluation worker, and Redis as one Docker Compose application named **talentmatch**. Open **https://localhost:7242**. LinkedIn always returns to:

```text
https://localhost:7242/auth/linkedin/callback
```

Only `127.0.0.1:7242` is published. API port 8000 and Redis are internal. Start/stop the existing application group with Docker Desktop's Play/Stop controls after initial setup. The gateway serves the frontend and API on the same HTTPS origin; no port-5173 frontend or separate Uvicorn HTTPS process is needed for this deployment.

## What the other person needs

- Docker Desktop running **Linux containers**, with Compose 2.24+ available (a current Docker Desktop release is recommended). Linux Docker Engine plus Compose is also supported.
- The exported runtime bundle: `images.tar`, runtime `compose.yml`, setup/start/stop scripts, `.env.example`, and instructions. No project source, Python, Node.js, Git or Visual Studio is required.
- Authorized runtime credentials in a private `.env` beside the supplied `compose.yml`.
- A compatible Linux image architecture. An archive built for `linux/amd64` needs an amd64-capable Docker runtime; an ARM host may need its own compatible build or supported emulation.
- Internet for the configured external LinkedIn, D365, Azure OpenAI, Azure Blob and optional Supabase services. Images can be imported offline; connected recruitment is not an offline application.

Images do not include `.env`, certificates, database contents, or uploaded resumes. Share secrets through an approved secure channel, never inside the public image or Git repository. Docker host administrators can inspect runtime environment values.

## 1. Build on the developer's machine

From PowerShell at the repository root, with Docker Desktop running:

```powershell
.\scripts\docker\build.ps1
```

On Linux/macOS:

```bash
./scripts/docker/build.sh
```

This builds `talentmatch-backend:phase1` for API/worker and `talentmatch-web:phase1` for the built React/gateway. Redis uses `redis:7.4-alpine`. Build-time downloads need network access. For an approved enterprise CA required by the build network, PowerShell supports `-BuildCaBundle C:\path\approved-ca.pem`; keep TLS verification enabled.

The portable deployment expects root `.env`. If it is absent and your existing `backend/.env` exists, the helper can copy it to root without modifying the original. Review the resulting settings. Do not overwrite a working `.env` with an example.

The connected Compose setup fixes `APP_ENV=production`, `DEMO_MODE=false`, the canonical HTTPS origins and LinkedIn callback. Configure the actual D365, Blob and AI credentials. Set HR credentials yourself; no built-in password is packaged.

## 2. Export a source-free transfer bundle

PowerShell:

```powershell
.\scripts\docker\export.ps1 -OutputDirectory .\dist\talentmatch
```

To build before exporting in one operation:

```powershell
.\scripts\docker\export.ps1 -OutputDirectory .\dist\talentmatch -Build
```

Linux/macOS:

```bash
./scripts/docker/export.sh ./dist/talentmatch
# Add --build when images have not yet been built.
./scripts/docker/export.sh ./dist/talentmatch --build
```

Transfer the **whole generated folder** or a ZIP of it. The archive contains backend, frontend/gateway and Redis images; the accompanying `image-platform.txt` identifies the architecture and `images.sha256` verifies archive content. The small runtime files describe how to connect the services. Do not transfer the source repository, a local CA private key, or a live `.env` inside an openly shared ZIP.

The image archive can be large. It belongs in approved file transfer or artifact storage, not a normal Git commit. The Dockerfiles, Compose files, scripts, example settings and documentation are versioned in GitHub so the bundle can be rebuilt.

## 3. Set up the recipient machine once

Extract the runtime folder to a normal writable location, for example `C:\TalentMatch`. Put the authorized `.env` there. Start Docker Desktop, open PowerShell in that folder, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

This loads the supplied image archive, creates a unique localhost certificate for this machine, trusts the public local root certificate in the current Windows user's Root store, and starts the Compose group. No additional Python or certificate utility is downloaded on the recipient system. Inspect the bundle and use your organization's script policy; the execution-policy argument applies to this process.

For Linux/macOS:

```bash
./setup.sh
```

Follow the host trust-store instructions printed by setup. Adding a root certificate may require administrator privileges. If host policy prohibits automated trust changes, use the script's `-SkipTrust` / `--skip-trust` option and have an administrator import the generated public root certificate through the approved process.

The certificate material under `.certs` is machine-specific. Its signing private key is not retained; the server private key remains local. Do not share that key. Trust must be installed for the OS/browser user opening the portal; Firefox or managed browser profiles can use a separate certificate store.

Open:

```text
https://localhost:7242
```

The browser must trust the certificate without an interstitial before testing LinkedIn. Register the exact callback in the LinkedIn developer application. `localhost` resolves to the machine where that browser runs; it does not open the developer's machine.

## 4. One Play action for later use

In Docker Desktop, choose **Containers → talentmatch → Play**. Start the application group, not only `web` or `api`. Compose health checks establish dependencies; the API and worker need Redis and metadata readiness. Open https://localhost:7242 once the group is running.

You can also run the supplied start wrapper:

```powershell
.\start.ps1
```

or:

```bash
./start.sh
```

Stop with Docker Desktop's group Stop action or `stop.ps1` / `stop.sh`. These preserve persistent volumes. The one-button experience begins **after** setup has created the containers; clicking Run on a single image in Docker Desktop cannot invent the other services, `.env`, volumes, and certificate trust.

After changing `.env`, use the start wrapper again so Compose recreates services with the changed configuration. Desktop Play restarts existing containers with their existing environment; it does not reload edited `.env` values.

## 5. Important runtime settings

```dotenv
HR_USERNAME=your-local-hr-user
HR_PASSWORD=choose-a-long-unique-password

D365_ENABLED=true
D365_CONTRACT_MODE=sqlite
D365_COMPANY=DAT

METADATA_BACKEND=sqlite
# For PostgreSQL/Supabase, use METADATA_BACKEND=postgres plus DATABASE_URL.
# Keep DATABASE_URL private and read docs/supabase.md before migration.

REDIS_PREFIX=talentmatch
# Omit REDIS_URL for the bundled Redis. Set it only for a shared private Redis.
```

The root runtime example lists all integration fields. Supply the actual D365 company, host, Entra service credentials and three operation paths; Azure OpenAI endpoint/key/deployment/API version; private Azure Blob container/connection; and LinkedIn credentials. Blank optional D365 history/detail/top-candidate paths remain blank under the three-operation contract.

The Compose gateway fixes these externally visible values:

```dotenv
FRONTEND_BASE_URL=https://localhost:7242
BACKEND_BASE_URL=https://localhost:7242
CORS_ALLOWED_ORIGINS=["https://localhost:7242"]
LINKEDIN_REDIRECT_URI=https://localhost:7242/auth/linkedin/callback
```

A host `.env` copied from native development may contain `REDIS_URL=redis://localhost:6379/0`. Inside a container `localhost` means that container, not the bundled Redis service. The helper normalizes a recognized plain native local Redis URL in copied or existing runtime configuration and preserves remote URLs. Review the resulting `.env`: omit `REDIS_URL` for bundled Redis or use `redis://redis:6379/0`.

Connected mode requires private Azure Blob. Local-resume storage is the development/demo adapter; setting a local directory does not replace configured Blob in production.

## 6. Moving existing application data

### Preserve native SQLite history before the first Docker start

If you already have real portal history in native `backend/.local/talentmatch.sqlite3`, a new Docker volume will otherwise appear empty. Either migrate to Supabase first using [the migration guide](supabase.md), or restore a consistent backup into the Docker volume **before the first setup/start**:

1. Stop native Uvicorn and the native worker, and stop any existing Docker API/worker. Keep your Blob container and ERP records unchanged.
2. Build/import the images and put the authorized root `.env` in place. From the source repository root, create a backup folder and use the existing native environment to back up SQLite:

```powershell
New-Item -ItemType Directory -Force .local\transfer | Out-Null
.\backend\.venv\Scripts\python.exe -c "import sqlite3; s=sqlite3.connect('backend/.local/talentmatch.sqlite3'); d=sqlite3.connect('.local/transfer/talentmatch.sqlite3'); s.backup(d); d.close(); s.close()"
```

Use your actual native database path if different. Transfer this backup separately and securely when moving to another host. No Python is required on the recipient for the restore step.

3. In the folder containing runtime `compose.yml` and `.env`, set the path to the backup folder and restore into the named volume with a one-off backend image:

```powershell
$backupFolder = (Resolve-Path .local\transfer).Path
docker compose run --rm --no-deps --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --volume "${backupFolder}:/transfer:ro" --entrypoint python api -c "import pathlib,sqlite3,os; p=pathlib.Path('/app/data/talentmatch.sqlite3'); assert not p.exists(), 'Target database already exists; stop and review instead of overwriting it'; s=sqlite3.connect('file:/transfer/talentmatch.sqlite3?mode=ro',uri=True); d=sqlite3.connect(str(p)); s.backup(d); d.close(); s.close(); os.chown(p,10001,10001); os.chmod(p,384); print('SQLite backup restored; source unchanged')"
```

On a recipient without the source tree, `$backupFolder` may be a different existing folder, such as `(Resolve-Path C:\PrivateTransfer).Path`. The file inside it must be named `talentmatch.sqlite3`. The command reads only the backup, starts no services, and refuses to overwrite an existing target. If Docker has already created a target database, stop and reconcile that existing data with the operator; do not delete volumes blindly.

4. Run the setup/start helper. Both API and worker now use the restored `/app/data/talentmatch.sqlite3`. Verify an existing application and private resume before enabling new submissions. Keep the backup until restore is accepted.

This restores **metadata only**. Existing connected applications still need access to the same private Azure Blob account/container and matching F&O company/records.

### Image transfer and other stores

Image transfer moves software only. For a new recipient with no records, the configured metadata store starts empty. To preserve existing history:

- For SQLite, use the stopped-writer backup/restore procedure above. Do not use separate API/worker copies or bake private records into an image.
- For Supabase, follow [the explicit migration guide](supabase.md), then supply the same approved database settings to the relevant backend.
- Preserve original private Azure Blob documents and matching account/container access. The database stores references, not document bytes.
- Retain ERP records and stable application/evaluation identifiers. Back up Redis separately where sessions/queue recovery policy requires it.

Two PCs using the same PostgreSQL database **must not run independent local workers with independent Redis coordination**. Use one active connected worker stack per database, or deliberately configure all participating stacks with the same private `REDIS_URL`, `REDIS_PREFIX`, D365 company and Blob container. In the latter arrangement the bundled local Redis is unused by the application. Localhost binding protects each browser entry point; it does not supply cross-machine queue coordination.

## 7. Logs, checks, and common failures

From the runtime folder:

```powershell
docker compose ps
docker compose logs --follow api worker
docker compose logs --tail 100 web redis
```

The local health endpoint is `https://localhost:7242/api/health`. It does not prove that every external provider accepts its credentials. Use a synthetic complete application to verify the whole connected flow and the record in `UBHRMatchEvaluationTable`.

| Symptom | Check |
| --- | --- |
| Port 7242 already in use | Stop the existing native Uvicorn/old stack. Keep the registered callback port; do not silently change it. |
| Certificate warning | Run per-machine setup/trust under the browser user. Check localhost spelling and separate browser trust stores. Never disable TLS checks. |
| LinkedIn callback fails | Exact registered URI, provider credentials/product, browser cookies, canonical localhost URL and service logs |
| API/worker cannot reach Redis | Container URL must use service `redis`, or the shared private endpoint; host localhost is not Redis inside another container. |
| AI processing fails | Worker logs: extraction, AI configuration, structured/evidence validation, or ERP save. Candidate pages hide these internal diagnostics. |
| ERP save HTTP 500 | Deployed service validation, legal entity, ID lengths, enums and the four Memo mappings; inspect safe correlation diagnostics. |
| Application group starts but jobs empty | Live D365 credentials/company, requirement open status and inclusive date criteria |
| No application history on a second PC | Metadata volumes are local unless migrated/shared; image import does not transfer records. |
| Changed `.env` has no effect | Run start wrapper to recreate configuration, rather than Desktop Play alone. |
| Missing images | Re-import complete `images.tar`; start wrappers do not build/download application images. |
| Wrong architecture | Export a compatible build or enable supported emulation; `image-platform.txt` records the built platform. |

Do not run `docker compose down --volumes` unless you intend to delete local metadata and Redis data. For upgrades, retain volumes and `.env`, import the new archive, then run the new start wrapper. Keep a tested backup and previous image version for rollback.

## Production boundary

This is a local HTTPS connected deployment with production-mode backend validation. It is not a publicly exposed internet service or a certified enterprise environment. Organizational rollout still needs reviewed HR identity, provider permissions, document security, backup/restore, retention, monitoring and availability. See [deployment](deployment.md), [technical reference](technical-reference.md), and the [current validation record](validation.md).
