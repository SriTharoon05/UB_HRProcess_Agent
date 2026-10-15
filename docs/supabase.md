# Move portal metadata from SQLite to Supabase PostgreSQL

Supabase PostgreSQL can replace the local SQLite **metadata store**. F&O continues to own jobs/candidates/applications/core evaluations; private Azure Blob continues to store original documents; Redis continues to hold sessions, queues and locks. The frontend still calls FastAPI; it never receives database credentials or Supabase keys.

## 1. Create the database and copy its real connection string

1. Create a Supabase project in the organization-approved region and set a strong database password. Keep that password in your approved secret store.
2. In the project's **Connect** dialog, select the PostgreSQL connection string. If your runtime has usable IPv6, the direct database endpoint is an option. For an IPv4-only machine/network, use the displayed **Session pooler** endpoint on port 5432.
3. Copy the exact displayed host and username. Pooler hostnames and usernames are project/region-specific; do not invent them from the project URL. Transaction pooler port 6543 is also supported by this driver; prepared statements are disabled for compatibility.
4. URL-encode reserved characters in the password when embedding it in a URI: for example `@` becomes `%40`, `#` becomes `%23`, and `%` becomes `%25`. Do not paste a raw password containing delimiters into the URL.
5. Use a dedicated server-side database role with approved privileges. Initial application schema creation requires appropriate schema/table privileges. Do not expose its connection string to a browser or a public repository.

The Supabase dashboard URL, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` are not required by this PostgreSQL adapter. An API key is not a PostgreSQL password.

## 2. Add backend environment settings

For native runs put these in `backend/.env`. For the portable Docker bundle put them in the `.env` beside `compose.yml`.

```dotenv
# The existing lean ERP contract name stays unchanged.
D365_CONTRACT_MODE=sqlite

# Select the actual portal metadata storage engine.
METADATA_BACKEND=postgres
DATABASE_URL=postgresql://YOUR_DATABASE_USERNAME:URL_ENCODED_PASSWORD@YOUR_ACTUAL_DATABASE_HOST:5432/postgres
DATABASE_SSLMODE=verify-full
DATABASE_SSLROOTCERT=
DATABASE_CONNECT_TIMEOUT=10
```

`DATABASE_URL` above is a template: use the exact Connect-dialog username/host. `DATABASE_SSLMODE=verify-full` validates the certificate chain and hostname. If the database's issuer is absent from the runtime's OS trust, download the trusted database CA from the provider's documented location and set `DATABASE_SSLROOTCERT` to its **runtime-visible** path. A Windows path cannot be used directly inside a Linux container; mount the CA file read-only and point the setting to the container path. Do not set TLS verification off to resolve a certificate error.

The CA bundle is public trust material, not a database secret. A private CA signing key is not needed. Local Docker's HTTPS localhost CA and the Supabase database CA serve different connections.

If a provider CA is needed in Docker, copy its public certificate into the persistent data volume once. API and worker share this volume:

```powershell
docker compose cp .\supabase-ca.pem api:/app/data/supabase-ca.pem
```

Then set `DATABASE_SSLROOTCERT=/app/data/supabase-ca.pem` in the runtime `.env` and run the supplied start wrapper again. Keep the file readable by container user 10001. A new machine using its own data volume also needs this public CA file when that setting is used. Leave the setting blank when the normal system trust store verifies the database certificate.

The code accepts `DATABASE_SSLMODE=disable` only for loopback local testing; it is not a Supabase deployment setting. `DATABASE_CONNECT_TIMEOUT` defaults to 10 seconds and permits 1–60. `SQLITE_DATABASE_PATH` remains useful only for local SQLite mode and the retained source backup.

## 3. Plan the cutover before starting a second system

A database URL lets multiple backend processes reach metadata; it does not coordinate independent queues. Choose one:

- **Simplest handoff:** run one active connected API/worker stack for that metadata database at a time. Stop the old machine before starting the replacement.
- **Deliberately shared deployment:** all participating API/worker stacks use the same private Redis endpoint, `REDIS_PREFIX`, company configuration and private Blob container. Set the same external `REDIS_URL`; separate bundled per-PC Redis services are not sufficient for concurrent workers.

Do not run multiple independent local workers against the same cloud metadata database. Recovery scans shared application outbox rows while locks/deduplication live in Redis, so different Redis servers cannot coordinate that work.

Confirm the Supabase plan's connection limits, backups, storage, region, network policy and availability for your intended use. Cloud metadata is not a guarantee of application availability; the backend and integrations must also be running.

## 4. Stop writers and back up SQLite

Stop **all** API/worker instances that could write source or target metadata. With Docker, stop the application group. With native runs, stop both Uvicorn and the worker. Keep original resume storage intact.

For a native repository, take a consistent backup from `backend` after stopping writers:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; s=sqlite3.connect('.local/talentmatch.sqlite3'); d=sqlite3.connect('.local/talentmatch-backup.sqlite3'); s.backup(d); d.close(); s.close()"
```

Use the actual `SQLITE_DATABASE_PATH` if different. Python's backup API handles SQLite/WAL correctly. Do not copy just the main file while a writer is active. Restrict access to the backup because it contains candidate/contact and document metadata.

A source-free Docker operator can back up the existing named volume using only Docker. With the application stopped, from the runtime folder:

```powershell
New-Item -ItemType Directory -Force .local\backup | Out-Null
$backupFolder = (Resolve-Path .local\backup).Path
docker compose run --rm --no-deps --user 0:0 --cap-add DAC_OVERRIDE --volume "${backupFolder}:/backup" --entrypoint python api -c "import sqlite3; s=sqlite3.connect('file:/app/data/talentmatch.sqlite3?mode=ro',uri=True); d=sqlite3.connect('/backup/talentmatch-backup.sqlite3'); s.backup(d); d.close(); s.close(); print('Consistent metadata backup saved')"
```

Keep the output folder private. The migration command below reads the existing database in the shared volume; a Windows source path needs an explicit bind mount. To move native history into that volume before migration, use the [first-start restore procedure](docker-local.md#preserve-native-sqlite-history-before-the-first-docker-start).

## 5. Dry-run source validation

From native `backend`, first add `DATABASE_URL` and TLS settings but keep `METADATA_BACKEND=sqlite` until the import has succeeded:

```powershell
.\.venv\Scripts\python.exe -m app.migrate_metadata --source .local\talentmatch.sqlite3 --dry-run
```

Or use `uv run --frozen python` in place of the virtual-environment Python. The dry run validates the **source only**, reports row counts, and does not connect to or mutate PostgreSQL. It therefore does not prove the database credentials or network are correct.

For Docker, the API/worker must remain stopped while a one-off container imports the source from the existing shared volume:

```powershell
docker compose run --rm --no-deps api python -m app.migrate_metadata --source /app/data/talentmatch.sqlite3 --dry-run
```

The source path must match the persisted database path in your bundle. Keep the target `DATABASE_URL`/TLS settings in root `.env`; normal Compose API initialization is bypassed by this explicit migration command.

## 6. Import transactionally

Remove only `--dry-run`:

```powershell
.\.venv\Scripts\python.exe -m app.migrate_metadata --source .local\talentmatch.sqlite3
```

Docker equivalent:

```powershell
docker compose run --rm --no-deps api python -m app.migrate_metadata --source /app/data/talentmatch.sqlite3
```

The command uses `DATABASE_URL` for the target even while `METADATA_BACKEND=sqlite`. It initializes the dedicated versioned schema and imports the application and evaluation-state data in one data transaction. Original identifiers, ownership, frozen snapshots and cached AI state are preserved.

Identical reruns insert nothing for already matching rows. Existing data that conflicts with a source record causes an error and rolls back the data import. Source SQLite is not changed or deleted. Review the safe JSON count summary; do not paste database URLs into terminal output or shared logs.

## 7. Switch storage and restart

After successful import, change:

```dotenv
METADATA_BACKEND=postgres
```

Restart both API and worker with the same `.env`. In the portable bundle use `start.ps1` / `start.sh` to recreate containers with the new environment; Desktop Play alone does not reload `.env`.

Verify an existing candidate-owned application, HR job list/detail, private resume download and completed/cached evaluation. Submit one synthetic new application and confirm its metadata and core ERP evaluation. Check that the source record counts and IDs are represented and that no duplicate application/evaluation was created. Retain the SQLite backup until the cutover and restore procedures are accepted.

## 8. Database visibility and security

The application creates a dedicated `talentmatch` schema with `applications`, `evaluation_states` and `schema_version`. Supabase's table browser may initially show only `public`; select the dedicated schema to inspect the metadata tables.

The adapter enables row-level security on its application tables and does not add public policies or grants. The backend uses its server-side database role. Keep the schema outside browser-facing exposed APIs; do not create anonymous read/write policies to make a dashboard table appear. Candidate ownership and HR role checks also remain enforced in FastAPI.

SQL-level content includes JSON snapshots, contact/profile data, private document references and AI evidence. Grant operator access deliberately and protect backups/exports. The application does not implement full cross-system record erasure or an enterprise audit ledger.

## 9. Rollback and ongoing backups

If import fails, keep `METADATA_BACKEND=sqlite`, preserve source, fix the reported target/source issue and rerun. If the new PostgreSQL deployment has already accepted writes, do not switch back to the old SQLite snapshot blindly: new records would disappear from portal views and diverge from ERP. Stop writers and reconcile/export those records through a reviewed restore/migration plan first.

Use the Supabase backup/PITR capability appropriate to your plan or a scheduled encrypted PostgreSQL backup, then test restoration. Back up private Blob documents and coordinate stable ERP IDs separately. A healthy database backup alone cannot restore deleted document bytes or ERP data. `RETENTION_DAYS` does not delete cloud metadata or replace a privacy/retention policy.

See [Docker handoff](docker-local.md), [environment settings](environment.md), and [technical reference](technical-reference.md).
