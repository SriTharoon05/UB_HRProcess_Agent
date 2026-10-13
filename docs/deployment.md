# Production deployment and operations

The included Compose configuration is a local demo. A connected production deployment needs configured identity providers, verified D365 contracts, private Azure services, Redis, and a separately running evaluation worker. External resources and X++ services are not provisioned by this repository.

The supplied connected override uses the configured backend environment and explicitly switches both API and worker to production mode. After populating `backend/.env`, registering HTTPS callbacks, and deploying the required X++ operations, run from the repository root:

```bash
TALENTMATCH_PUBLIC_URL=https://recruitment.example.com docker compose -f compose.yml -f compose.production.yml --profile connected up --build -d
```

Replace the example origin with your actual HTTPS ingress origin; do not include a path or trailing slash. The override sets matching frontend/backend URLs and JSON CORS origins. It does not create an HTTPS ingress, Azure resources, provider registrations, or D365 operations, and live connected deployment is unverified. Its internal Redis is isolated on the Compose network but needs your reviewed persistence/access/backup arrangement for the target production environment.

## Recommended service arrangement

Serve the built frontend through an HTTPS gateway/static host. Route `/api` and `/auth` to FastAPI under the same externally visible origin. Deploy API and worker as separate supervised services, for example Azure Container Apps or App Service plus an appropriate worker service. Use the same application configuration, private Blob container, and Redis service/prefix for both. The worker command is:

```bash
python -m app.worker
```

Build the frontend with `npm ci && npm run build`; deploy `frontend/dist` with a React Router fallback to `index.html`. The nginx container includes the API/auth proxy and routing fallback. Run Uvicorn behind the gateway; restrict trust in forwarded headers to the actual proxy and do not expose an administrative API or Redis directly to the internet.

When a managed network uses its own trusted certificate authority, both Dockerfiles accept an optional BuildKit `build_ca_bundle` secret containing the approved CA bundle. Pass it with `--secret id=build_ca_bundle,src=/path/to/approved-ca-bundle.pem` and the network's supported proxy settings. The bundle is mounted only during dependency installation. Package TLS and artifact verification remain enabled; normal public-network builds use standard trust roots.

## Minimum connected configuration

Set `APP_ENV=production`, `DEMO_MODE=false`, `D365_ENABLED=true`, HTTPS `FRONTEND_BASE_URL`/`BACKEND_BASE_URL`, and an explicit JSON `CORS_ALLOWED_ORIGINS` allowlist. Configure exact HTTPS OAuth callbacks, LinkedIn credentials, tenant-specific HR credentials/roles, D365 service credentials, private Blob settings, Azure OpenAI deployment settings, and private Redis.

Production configuration rejects demo mode, non-HTTPS portal/backend URLs, wildcard CORS, and non-HTTPS allowed origins. Cookies are Secure/HttpOnly/SameSite=Lax in production. Prefer same-origin hosting so cookies, callback state, and CSRF checks have one clear trust boundary.

Supply credentials from the runtime secret store, preferably Azure Key Vault references or your orchestrator's secret injection. Do not embed secrets in images, source, frontend assets, saved cloud setup scripts, or command-line arguments. This implementation accepts environment-injected credentials; it does not claim a deployed Key Vault integration or managed-identity authentication path. Rotate secrets and redeploy/restart services when their values change.

## D365 acceptance gate

The resource application must be registered/authorized in D365 with least-privilege access to the required custom services. Check the token resource scope, configured company, existing request/response mapping, stable application identifiers, server-side submission uniqueness, and one-evaluation-per-application upsert.

Deploy `saveCandidateEvaluation` and `getTopCandidates` separately in X++. Keep their `.env.example` values empty until actual paths are verified. Candidate-owned history/details, unrestricted single-application access, persistent failure status, HR status updates, and deletion are additional capabilities requiring confirmed contracts. Selected-job HR detail/resume access can use the trusted top-100 ranking response until a single-application read is available. See [D365 schema](d365-schema.md) and [D365 endpoints](d365-endpoints.md).

## Redis durability and recovery

Use a dedicated private Redis service with authentication, TLS where available, persistence, and appropriate backup/availability. Sessions, idempotency coordination, submission outbox, queued jobs, and temporary evaluation state are sensitive. Restrict access to the API/worker, isolate tenants/environments, and avoid an eviction policy that discards active jobs or session state. Monitor available memory, queue latency, worker liveness, failed jobs, and persistence/backup health.

The API durably stores the submission intent before calling D365, records its confirmed application ID, then queues evaluation. The worker reconciles unfinished submission outbox records at startup and periodically. The queue carries document references and job context, not OAuth tokens or raw resume text. Temporary state may still include contact metadata, job snapshots, and validated evaluation excerpts; protect it and its backups accordingly.

Transient evaluation failures retry with bounded exponential backoff. Cached validated output is reused after a D365 save failure, avoiding another model-generated score on a persistence retry. Completed state avoids unnecessary repeated work. This still requires D365-side idempotency: an HTTP timeout can occur after D365 has already committed, and Redis may be lost/restored independently.

After fixing a missing endpoint or credential, restart API/worker with the new environment and requeue retained failed work:

```bash
cd backend
uv run --frozen python -m app.retry_evaluation APP-000125
```

Use the real application ID. The recovery command requires exactly one retained submission, rejects a running/already-queued evaluation, and does not rerun completed work. It preserves cached validated AI output to retry only the failed persistence step where possible. Do not delete temporary state or upload a duplicate application just to rerun evaluation. Terminal errors and stored pending output must be reviewed before their retention expiry. Failed/Processing state in Redis is not proof that D365's business status was updated.

## Private documents

Create the Blob container in advance with public access disabled. The adapter checks container privacy and uses generated opaque object names. It rejects connected local storage and does not issue public URLs. HR downloads pass through a backend role check and a trusted D365 application/storage reference. Apply storage-account firewall/private endpoints, least-privilege access, encryption, region policy, and operational access auditing as required by your organization.

Local demo documents are stored in an ignored private directory with restrictive file permissions. They are real uploads; do not use sensitive candidate documents in a development/demo environment. PDF/DOCX structural validation is not antivirus scanning. Where required, integrate an approved malware scanner/quarantine pipeline before making uploaded documents available to reviewers.

## Retention and deletion

`RETENTION_DAYS` controls temporary submission/idempotency/evaluation-state expiry; `SESSION_TTL_SECONDS` controls sessions. Document and business-record deletion are separate policies, not automatic effects of that variable. Set values to the approved policy, not merely the defaults. Coordinate Redis expiry, Blob lifecycle/soft-delete/versioning, D365 records/evaluations, exported data, and backup retention. Scheduled cleanup and operational deletion must account for active retries and lawful retention exceptions.

The private-storage adapter supports deletion, but the repository does not automatically delete business records or implement a cross-system cleanup command. Configure a reviewed Azure Blob lifecycle rule for production documents. Manually remove expired demo documents only after checking that no active application/test needs them. A deletion in Blob is not a deletion in D365: define a supported X++ business-record deletion/anonymization procedure and subject-request authorization separately. The four main services do not provide that write contract. Do not claim a complete cross-system erasure because a document or Redis key expired.

Publish a reviewed privacy notice, version it with `CONSENT_VERSION`, and capture explicit consent before submission. The prompt minimizes obvious identifiers but does not guarantee anonymization. Review regional/provider handling for sending candidate resume text to Azure OpenAI and limit access to relevant HR users.

## Observability and health

`GET /api/health` reports application health/mode; it is not a certificate that all external credentials, callbacks, or X++ contracts work. Check API, worker, Redis, storage, D365, and Azure OpenAI separately during rollout. Logs should record operation category, safe status, and correlation ID, not tokens, secrets, raw resumes, provider response bodies, or unnecessary candidate details.

Run a live acceptance flow with a synthetic text-based resume: authenticate, read a real open job, submit once, retry the same request, observe worker progression, verify the evaluation in D365, inspect job-specific HR evidence, and download the authorized original. Check cross-role/cross-owner denial and a missing integration path. The repository test suite uses mocks and cannot replace these live deployment checks.

## Human review

Retain visible AI labels and evidence/context in the HR workspace. A score is approximate evidence alignment, not candidate worth or a hiring recommendation. Quotes can be real while the model's reasoning is incorrect. Missing resume evidence does not establish missing ability. No score threshold automatically accepts/rejects candidates, and no HR status mutation is offered without a supported D365 write.
