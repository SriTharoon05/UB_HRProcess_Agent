# Production deployment and operations

The included Compose configuration is a local demo. A connected production deployment needs configured identity providers, verified D365 contracts, private Azure services, Redis, and a separately running evaluation worker. External resources and X++ services are not provisioned by this repository.

The supplied connected override uses the configured backend environment and explicitly switches both API and worker to production mode. After populating `backend/.env`, registering HTTPS callbacks, and deploying the required X++ operations, run from the repository root:

```bash
TALENTMATCH_PUBLIC_URL=https://recruitment.example.com docker compose -f compose.yml -f compose.production.yml --profile connected up --build -d
```

Replace the example origin with your actual HTTPS ingress origin; do not include a path or trailing slash. The override sets matching frontend/backend URLs and JSON CORS origins. It does not create an HTTPS ingress, Azure resources, provider registrations, or D365 operations, and live connected deployment is unverified. Its internal Redis is isolated on the Compose network but needs your reviewed persistence/access/backup arrangement for the target production environment.

## Recommended service arrangement

Serve the built frontend through an HTTPS gateway/static host. Route `/api` and `/auth` to FastAPI under the same externally visible origin. Deploy API and worker as separate supervised services, for example Azure Container Apps or App Service plus an appropriate worker service. Use the same application configuration, private Blob container, Redis service/prefix and durable SQLite database for both. The worker command is:

```bash
python -m app.worker
```

Build the frontend with `npm ci && npm run build`; deploy `frontend/dist` with a React Router fallback to `index.html`. The nginx container includes the API/auth proxy and routing fallback. Run Uvicorn behind the gateway; restrict trust in forwarded headers to the actual proxy and do not expose an administrative API or Redis directly to the internet.

When a managed network uses its own trusted certificate authority, both Dockerfiles accept an optional BuildKit `build_ca_bundle` secret containing the approved CA bundle. Pass it with `--secret id=build_ca_bundle,src=/path/to/approved-ca-bundle.pem` and the network's supported proxy settings. The bundle is mounted only during dependency installation. Package TLS and artifact verification remain enabled; normal public-network builds use standard trust roots.

## Minimum connected configuration

Set `APP_ENV=production`, `DEMO_MODE=false`, `D365_ENABLED=true`, `D365_CONTRACT_MODE=sqlite`, a shared absolute `SQLITE_DATABASE_PATH`, HTTPS `FRONTEND_BASE_URL`/`BACKEND_BASE_URL`, and an explicit JSON `CORS_ALLOWED_ORIGINS` allowlist. Configure exact HTTPS OAuth callbacks, LinkedIn credentials, tenant-specific HR credentials/roles, D365 service credentials, private Blob settings, Azure OpenAI deployment settings, and private Redis.

Production configuration rejects demo mode, non-HTTPS portal/backend URLs, wildcard CORS, and non-HTTPS allowed origins. Cookies are Secure/HttpOnly/SameSite=Lax in production. Prefer same-origin hosting so cookies, callback state, and CSRF checks have one clear trust boundary.

Supply credentials from the runtime secret store, preferably Azure Key Vault references or your orchestrator's secret injection. Do not embed secrets in images, source, frontend assets, saved cloud setup scripts, or command-line arguments. This implementation accepts environment-injected credentials; it does not claim a deployed Key Vault integration or managed-identity authentication path. Rotate secrets and redeploy/restart services when their values change.

## D365 acceptance gate

The resource application must be registered/authorized in D365 with least-privilege access to the required custom services. Check the token resource scope, configured company, existing request/response mapping, stable application identifiers, server-side submission uniqueness, and one-evaluation-per-application upsert.

Deploy the three source-pack operations `getOpenRequirements`, `submitApplication`, `saveCandidateEvaluation` under `UBHRPortalServiceGroup/UBHRPortalService`. Existing screenshot tables are used; no new D365 columns/EDTs/enums are required. Inspect existing ID lengths and unique indexes, actual enum symbols, company scope and table defaults before acceptance. SQLite mode reads history/detail/ranking locally, so no additional read-service endpoints are needed. These reads cover only acknowledged portal submissions; external F&O recruiter edits are not synchronized. See [D365 schema](d365-schema.md) and [D365 endpoints](d365-endpoints.md).

## SQLite durability and deployment scope

The default three-operation adapter uses SQLite as durable portal storage. It contains candidate/contact/profile snapshots, consent, resume references/checksums, full JD snapshots, request keys/outbox acknowledgements, timestamps and complete validated evaluations including provenance. Actual uploaded documents stay in private Blob Storage.

API and worker must resolve `SQLITE_DATABASE_PATH` to **the same file on a shared local persistent volume**. The connected Compose override uses `/app/data/talentmatch.sqlite3` in both services and a common named volume. Retain that volume when restarting services; `docker compose down --volumes` removes persistent local data. Restrict directory access to the application identity and use disk/volume encryption and reviewed backup access.

This arrangement supports one host/shared local volume. WAL-mode SQLite does not support independent database copies on different hosts or an SMB/NFS-mounted file. Do not scale API/worker replicas across machines under that configuration; use a reviewed server database migration for multi-host deployment.

Use SQLite's online backup API or stop writers for a consistent backup; blindly copying only the `.sqlite3` file while its WAL is active can lose committed data. Test restore together with F&O IDs, private Blob documents and queue recovery. SQLite data is not an expendable Redis cache and is not automatically deleted by `RETENTION_DAYS`.

## Redis durability and recovery

Use a dedicated private Redis service with authentication, TLS where available, persistence, and appropriate backup/availability. In SQLite mode Redis carries sessions, locks and queued job arguments; the submission outbox and full evaluation state are durable SQLite records. Legacy mode also retains submission/evaluation cache state in Redis. Restrict access to the API/worker, isolate tenants/environments, and avoid an eviction policy that discards active jobs or session state. Monitor available memory, queue latency, worker liveness, failed jobs, and persistence/backup health.

The API durably stores the frozen submission intent and stable application ID in SQLite before calling D365, records its acknowledgement, then queues evaluation. The worker reconciles unfinished submission outbox records at startup and periodically. The queue carries document references and job context, not OAuth tokens or raw resume text. SQLite retains contact metadata, job snapshots and validated evaluations; temporary coordination can also include sensitive metadata. Protect both stores and their backups accordingly.

Transient evaluation failures retry with bounded exponential backoff. Cached validated output is reused after a D365 save failure, avoiding another model-generated score on a persistence retry. Completed state avoids unnecessary repeated work. This still requires D365-side stable-ID uniqueness: an HTTP timeout can occur after F&O has already committed, while SQLite/Redis can be restored independently.

After fixing a missing endpoint or credential, restart API/worker with the new environment and requeue retained failed work:

```bash
cd backend
uv run --frozen python -m app.retry_evaluation APP-000125
```

Use the real application ID. The recovery command requires exactly one retained submission, rejects a running/already-queued evaluation, and does not rerun completed work. It preserves cached validated AI output to retry only the failed persistence step where possible. Do not delete temporary state or upload a duplicate application just to rerun evaluation. Terminal errors and stored pending output must be reviewed before their retention expiry. Failed/Processing state is recorded locally and is not proof that D365's business status was updated. SQLite exposes the complete result only after the matching F&O evaluation acknowledgement.

## Private documents

Create the Blob container in advance with public access disabled. The adapter checks container privacy and uses generated opaque object names. It rejects connected local storage and does not issue public URLs. HR downloads pass through a backend role check and a trusted acknowledged SQLite application/storage reference in the three-operation mode. Apply storage-account firewall/private endpoints, least-privilege access, encryption, region policy, and operational access auditing as required by your organization.

Local demo documents are stored in an ignored private directory with restrictive file permissions. They are real uploads; do not use sensitive candidate documents in a development/demo environment. PDF/DOCX structural validation is not antivirus scanning. Where required, integrate an approved malware scanner/quarantine pipeline before making uploaded documents available to reviewers.

## Retention and deletion

`RETENTION_DAYS` controls temporary submission/idempotency/evaluation-state expiry; `SESSION_TTL_SECONDS` controls sessions. Document and business-record deletion are separate policies, not automatic effects of that variable. Set values to the approved policy, not merely the defaults. Coordinate Redis expiry, SQLite application/profile/evaluation records, Blob lifecycle/soft-delete/versioning, D365 records/evaluations, exported data and backup retention. Scheduled cleanup and operational deletion must account for active retries and lawful retention exceptions.

The private-storage adapter supports deletion, but the repository does not automatically delete business records or implement a cross-system cleanup command. Configure a reviewed Azure Blob lifecycle rule for production documents. Manually remove expired demo documents only after checking that no active application/test needs them. A deletion in Blob is not a deletion in D365: define a supported X++ business-record deletion/anonymization procedure and subject-request authorization separately. The three F&O service operations do not provide that deletion contract. Do not claim a complete cross-system erasure because a document or Redis key expired.

Publish a reviewed privacy notice, version it with `CONSENT_VERSION`, and capture explicit consent before submission. The prompt minimizes obvious identifiers but does not guarantee anonymization. Review regional/provider handling for sending candidate resume text to Azure OpenAI and limit access to relevant HR users.

## Observability and health

`GET /api/health` reports application health/mode; it is not a certificate that all external credentials, callbacks, or X++ contracts work. Check API, worker, Redis, storage, D365, and Azure OpenAI separately during rollout. Logs should record operation category, safe status, and correlation ID, not tokens, secrets, raw resumes, provider response bodies, or unnecessary candidate details.

Run a live acceptance flow with a synthetic text-based resume: authenticate, read a real open job, submit once, retry the same request, observe worker progression, verify the evaluation in D365, inspect job-specific HR evidence, and download the authorized original. Check cross-role/cross-owner denial and a missing integration path. The repository test suite uses mocks and cannot replace these live deployment checks.

## Human review

Retain visible AI labels and evidence/context in the HR workspace. A score is approximate evidence alignment, not candidate worth or a hiring recommendation. Quotes can be real while the model's reasoning is incorrect. Missing resume evidence does not establish missing ability. No score threshold automatically accepts/rejects candidates, and no HR status mutation is offered without a supported D365 write.
