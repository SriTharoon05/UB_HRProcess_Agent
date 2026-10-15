# Deployment and operations

The supported local connected package is a Docker Compose application with HTTPS frontend gateway, API, worker and Redis. Its only published port is `127.0.0.1:7242`; the portal and LinkedIn callback use **https://localhost:7242**. Follow [Docker setup and source-free transfer](docker-local.md) for exact build/export/import and one-time certificate trust instructions.

This is a local production-mode deployment of Phase 1. It does not provision external services or establish organizational production approval. Public cloud hosting requires its own DNS, ingress, callbacks, secrets, networking, capacity and operations design.

## Runtime configuration and service arrangement

Root `.env` is the portable Docker runtime configuration. Native development uses `backend/.env` from the backend working directory. Do not overwrite a working configuration with an example. API and worker must share metadata engine/connection, Redis endpoint/prefix, D365 company, private Blob and model settings.

The connected Compose file fixes production mode, disables demo and sets the canonical HTTPS origins/callback. It serves built static assets and proxies `/api` and `/auth` to the internal HTTP API. Redis has no published host port; the local Compose network is the access boundary. The local Redis instance has persistence and no password; use an authenticated private/TLS endpoint when infrastructure crosses trust boundaries. `REDIS_URL` can override the bundled service.

After changing `.env`, run the setup/start wrapper to recreate containers with the new environment. Desktop Play restarts an existing container configuration, not edited dotenv settings. Docker images never include `.env` or data volumes. Secret rotation requires restart/recreation of affected services.

For a separately managed deployment, supervise API and worker independently behind a trusted same-origin HTTPS gateway. Run the worker with `python -m app.worker`. Restrict forwarded-header trust to the actual gateway and do not expose private Redis/database or administrative interfaces publicly. Use approved runtime secret injection rather than secrets baked into images or frontend assets.

## Minimum connected configuration

Configure LinkedIn OIDC client/secret and exact callback; backend-only `HR_USERNAME`/`HR_PASSWORD`; D365 service-app credentials, company and three operation paths; Azure OpenAI endpoint/key/deployment/API version; private Azure Blob; Redis; and a durable metadata store. Production rejects demo mode, non-HTTPS browser origins, wildcard CORS and public/local document fallback.

The current HR account is one environment-configured shared account. Broader enterprise rollout should use named organizational identities, MFA/SSO, least privilege and suitable audit attribution. Password matching is exact; choose and protect a strong unique value. Keep D365 service-app Entra credentials separate from HR sign-in.

See [environment settings](environment.md), [authentication](linkedin-auth.md), and [AI behavior](azure-openai.md).

## Metadata durability

SQLite is default: API/worker share `/app/data/talentmatch.sqlite3` in one persistent local volume. Do not use independent copies, SMB/NFS or multiple hosts with a shared WAL file. Retain volumes across upgrades. `docker compose down --volumes` destroys local portal and Redis data.

PostgreSQL/Supabase is optional through `METADATA_BACKEND=postgres`, server-only `DATABASE_URL`, `DATABASE_SSLMODE=verify-full`, and optional trusted `DATABASE_SSLROOTCERT`. The separate `D365_CONTRACT_MODE=sqlite` remains the three-operation ERP contract. Follow the explicit stopped-writer, atomic, conflict-detecting [migration procedure](supabase.md); image transfer does not migrate data.

Start with one active connected stack per metadata database. Deliberate multiple-stack deployments should share private Redis/prefix, D365 company and Blob storage. Database evaluation locks supplement retry safety but do not replace queue/session coordination. Independent per-PC Redis with a shared PostgreSQL database is not the recommended deployment model.

## ERP acceptance

Deploy `getOpenRequirements`, `submitApplication`, and `saveCandidateEvaluation` under `UBHRPortalServiceGroup/UBHRPortalService` using the existing four tables in model `UBHR_Nive`. Validate company scope, actual enums, EDT/ID sizes, table defaults, unique indexes, stable-ID reuse and boolean/matching-ID response contracts. The four evaluation Memo fields must be accepted by the service.

Only these three paths are needed. Leave optional history/detail/top-candidate read paths empty under this contract; metadata serves acknowledged portal records. Existing ERP-only history and recruiter status edits are not synchronized. The repository provides X++ source, not a compiled/deployed model. Live compilation, permissions and serializer acceptance remain F&O responsibilities.

## Queue durability and failed evaluations

Redis carries sessions, queue arguments, locks and temporary state; durable metadata contains outbox and validated evaluations. Use persistence, monitor memory/latency/backlog, and avoid evicting active jobs or sessions. The local bundle stores AOF in a named volume. A shared managed service needs reviewed authentication, TLS, access and backup settings.

The worker reconciles unfinished outbox records at startup and periodically. Transient failures retry with bounded backoff. Schema/evidence failures get a bounded correction loop; exhausted non-retryable failures await an explicit HR action after their cause is reviewed. Save-only retries reuse cached valid output rather than generate a new score.

HR can click **Retry evaluation** on a failed application and **Refresh list**. The endpoint is HR-only, CSRF-protected and rejects inappropriate active/completed work. A CLI is available when needed:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.retry_evaluation APP-REPLACE-WITH-REAL-ID
```

Do not delete durable state or submit a duplicate application to rerun processing. An HTTP timeout may occur after ERP committed; stable identifier uniqueness/upsert must make the repeated delivery safe. Internal `Failed` is an operational state, not a candidate rejection. Candidate pages do not expose it.

## Backup and restore

Maintain separate coordinated backups for metadata, private documents, ERP records, required Redis persistence and secret configuration. Image archives distribute application code, not data. Protect exports and test restoration against real stable-ID/document references.

For SQLite, use its online backup API or stop writers. Copying only the live main `.sqlite3` file while WAL is active can lose committed records. A new volume starts empty; retain/restores must target the same shared path. For PostgreSQL, use approved managed backups/PITR or encrypted logical backups and a tested restore plan. Do not switch back to an old SQLite snapshot after PostgreSQL accepted new writes without reconciliation.

Restore documents with their private object references and ensure ERP applications/evaluation identifiers still match. A database backup alone cannot restore deleted Blob files or ERP state. Named Docker volumes remain local to their host; transferring an image does not transfer them.

## Documents, retention and privacy

Connected mode requires an existing private Azure Blob container. The adapter checks privacy, uses opaque names, and serves HR downloads through backend authorization. Apply the organization's storage access, encryption, region, retention and incident policies. Format/structure validation is not malware scanning; add approved quarantine/scanning where required. OCR is not currently implemented.

`RETENTION_DAYS` expires temporary processing/idempotency state, not all metadata, Blob, ERP or backup records. Coordinate lawful retention, subject-request handling, deletion/anonymization and backups across systems. Cross-system automated erasure is not included. Consent must match `CONSENT_VERSION` and an approved privacy notice.

The model receives best-effort identity-minimized resume text, not guaranteed anonymous data. Approve external provider/region processing. AI scores are contextual evidence, not employment decisions or verified claims.

## Logs and health

Docker Desktop exposes individual service logs. From the runtime directory:

```powershell
docker compose ps
docker compose logs --follow api worker
```

`GET https://localhost:7242/api/health` checks the application/mode, not all external credentials. Terminal stages record start/completion/failure, elapsed time, application ID and safe D365 correlation diagnostics. `LOG_LEVEL=DEBUG` adds safe field shape details; raw credentials, OAuth query values, resume/model content and candidate contacts remain excluded. See [debugging](debugging.md).

The bundle caps Docker JSON logs at 10 MB × 3 per service. External deployments need reviewed collection, alerting, retention and operator access. Monitor worker liveness, queue age, repeated failure reasons, failed ERP deliveries, database/Blob capacity and certificate expiry.

## Rollout criteria and remaining work

Use a synthetic live flow to verify exact selected-job callback return, valid PDF/DOCX extraction, single ERP application creation, evidence checking, acknowledged evaluation save, HR retry, private document ownership/role enforcement and backup restoration. Local mock tests do not establish provider registration or X++ acceptance. Consult [validation](validation.md) for executed local results.

Remaining enterprise work includes named HR identity, approved document malware scanning/OCR, ERP status synchronization, cross-system erasure/audit, capacity/availability objectives, and reviewed operational controls. Future screening/interview/onboarding/employee-maintenance functions are roadmap, not current delivered scope. See the [technical](technical-reference.md) and [business](business-reference.md) references.
