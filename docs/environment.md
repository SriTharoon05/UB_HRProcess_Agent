# Environment configuration reference

FastAPI loads `backend/.env` when started from `backend/`, then applies process environment overrides through Pydantic Settings. The worker uses the same settings. Copy `.env.example` only if a local file does not already exist; keep real `.env` files and secrets out of Git. Restart affected API/worker processes after changing settings.

The default is `APP_ENV=development`, `DEMO_MODE=true`, and D365 disabled. This is the credential-free demo workflow. Connected mode selects only real integration adapters; missing configuration produces an explicit error. Production requires `APP_ENV=production`, `DEMO_MODE=false`, and HTTPS URLs/origins.

For list/dictionary values, use **JSON**, not comma-separated strings:

```dotenv
CORS_ALLOWED_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
HR_ALLOWED_ROLES=["HRRecruiter","HRAdministrator"]
D365_REQUEST_FIELD_MAPS={}
```

## Application, sessions, and processing

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `TalentMatch AI` | Backend application/API name |
| `APP_ENV` | `development` | `development`, `test`, or `production`; controls secure cookies/demo access |
| `DEMO_MODE` | `true` | Explicit fictional-data adapter and development sign-in; must be false in production |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | Browser-visible portal URL and successful-login redirect origin |
| `BACKEND_BASE_URL` | `http://localhost:8000` | Browser-visible backend origin for CSRF/origin validation |
| `CORS_ALLOWED_ORIGINS` | Localhost/127.0.0.1 port 5173 | Exact JSON origin list; wildcard is rejected; production origins require HTTPS |
| `SESSION_COOKIE_NAME` | `talentmatch_session` | Opaque session cookie name |
| `SESSION_TTL_SECONDS` | `28800` | Session expiry, 300–86400 seconds |
| `REDIS_URL` | `redis://localhost:6379/0` | Connected API/worker Redis; use private authenticated/TLS service in production |
| `REDIS_PREFIX` | `talentmatch` | Application namespace for temporary/session state; must agree across API and worker |
| `RETENTION_DAYS` | `90` | Temporary submission/idempotency/evaluation-state lifetime; align the separate document/business-record retention policy |
| `CONSENT_VERSION` | `v1` | Current privacy/processing consent version accepted by submissions |
| `PUBLIC_RATE_LIMIT` | `120` | Public requests per client IP per 60-second bucket |
| `UPLOAD_RATE_LIMIT` | `10` | Resume-submission requests per client IP per 60-second bucket |
| `EVALUATION_MAX_ATTEMPTS` | `5` | Bound for transient evaluation retry attempts |

Sessions store only a random reference in the browser and keep their data server-side. A `SESSION_SECRET` is not needed for this session design. Demo state is process-local; connected mode requires Redis. The supplied `APP_DEBUG` and `LOG_LEVEL` examples are not used as application configuration toggles unless explicitly implemented; they are omitted from the example instead of suggesting unsupported controls.

## LinkedIn and HR OIDC

| Variable | Default | Purpose |
| --- | --- | --- |
| `LINKEDIN_CLIENT_ID` | Empty | LinkedIn OIDC application identifier |
| `LINKEDIN_CLIENT_SECRET` | Empty | Backend-only LinkedIn secret |
| `LINKEDIN_REDIRECT_URI` | `http://localhost:8000/auth/linkedin/callback` | Exact registered externally visible callback |
| `LINKEDIN_ISSUER` | `https://www.linkedin.com/oauth` | Required issuer claim |
| `LINKEDIN_DISCOVERY_URL` | LinkedIn OAuth OIDC discovery URL | Trusted provider metadata/JWKS source |
| `HR_ENTRA_TENANT_ID` | Empty | Authorized HR tenant |
| `HR_ENTRA_CLIENT_ID` | Empty | HR web application registration |
| `HR_ENTRA_CLIENT_SECRET` | Empty | Backend-only HR registration secret |
| `HR_ENTRA_REDIRECT_URI` | `http://localhost:8000/auth/hr/callback` | Exact registered HR callback |
| `HR_ALLOWED_ROLES` | `["HRRecruiter","HRAdministrator","TalentMatch.HR"]` | Accepted application-role claim values as a JSON list |
| `ENTRA_HR_ROLE` | `TalentMatch.HR` | Additional accepted role; align with intended authorization policy |

Scopes are fixed to `openid profile email`. Additional LinkedIn history/phone/skills access is not implied. `FRONTEND_URL`, `BACKEND_URL`, `CORS_ORIGINS`, and the corresponding `ENTRA_*` identity variable aliases are accepted for compatibility; use the canonical names above in new configuration. See [authentication setup](linkedin-auth.md).

## D365 F&O

| Variable | Default | Purpose |
| --- | --- | --- |
| `D365_ENABLED` | `false` | Enable the connected D365 adapter |
| `D365_CONTRACT_MODE` | `sqlite` | Three screenshot-table operations; `legacy` explicitly selects the older six-operation adapter |
| `SQLITE_DATABASE_PATH` | `.local/talentmatch.sqlite3` | Durable portal metadata; API and worker must resolve this to the same local file |
| `D365_BASE_URL` | Supplied `org1a43c536.operations.dynamics.com` HTTPS resource | Resource origin; token scope is `<base>/.default` |
| `D365_TENANT_ID` | Empty | Service-app Entra tenant ID/domain |
| `D365_CLIENT_ID` | Empty | Registered service application authorized inside D365 |
| `D365_CLIENT_SECRET` | Empty | Backend-only service credential |
| `D365_COMPANY` | `DAT` | Legal entity for request-contract operations |
| `D365_PARAMETER_NAME` | `_request` | Default request-contract parameter name; per-operation wrapper overrides take priority |
| `D365_REQUIREMENT_PATH` | `.../UBHRPortalService/getOpenRequirements` | Relative POST custom-service path; requires source-pack deployment |
| `D365_SUBMIT_APPLICATION_PATH` | `.../UBHRPortalService/submitApplication` | Relative POST application service path; requires source-pack deployment |
| `D365_SAVE_EVALUATION_PATH` | `.../UBHRPortalService/saveCandidateEvaluation` | Relative POST save path; requires source-pack deployment |
| `D365_TOP_CANDIDATES_PATH` | Empty | Legacy adapter only; SQLite mode ranks acknowledged portal records locally |
| `D365_MY_APPLICATIONS_PATH` | Empty | Legacy adapter only; SQLite mode reads owned history locally |
| `D365_APPLICATION_PATH` | Empty | Legacy adapter only; SQLite mode reads acknowledged detail locally |
| `D365_HTTP_TIMEOUT` | `30` | HTTP timeout in seconds |
| `D365_REQUEST_WRAPPERS` | Per-operation object | Internal snake_case operation → X++ wrapper; `""` means flat body |
| `D365_REQUEST_FIELD_MAPS` | `{}` | Per-operation canonical snake_case key → actual request field |
| `D365_RESPONSE_FIELD_MAPS` | `{}` | Per-operation canonical snake_case key → actual response field |

The three source-pack paths and examples are in [D365 endpoints](d365-endpoints.md). The committed examples use `UBHRPortalServiceGroup/UBHRPortalService`; build/deploy those operations before enabling them. `getOpenRequirements` sends `{}` and uses the mapped F&O user's company; writes require matching `Company`. Wrappers/field aliases do not change service signatures.

SQLite stores the frozen application/profile/consent/document metadata and complete evaluation. Use a shared absolute local path for deployed API/worker processes; the Compose override uses `/app/data/talentmatch.sqlite3` on a common persistent volume. WAL-mode SQLite is for one host/local volume, not independent multi-host copies or SMB/NFS. History/ranking include only acknowledged portal submissions; external F&O recruiter edits are not synchronized. Actual PDF/DOCX bytes stay in private Blob Storage, and Redis remains the connected queue/session service.

## Azure OpenAI

| Variable | Default | Purpose |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Supplied Azure cognitive-services resource | Azure resource endpoint |
| `AZURE_OPENAI_API_KEY` | Empty | Backend-only API credential |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4.1-mini` | Azure deployment name supporting structured output |
| `AZURE_OPENAI_API_VERSION` | `2025-03-01-preview` | Configurable API version; verify with the deployment |
| `AZURE_OPENAI_PROMPT_VERSION` | `v1` | Installed `evaluation_vN.txt` prompt version |
| `AZURE_OPENAI_MAX_RESUME_CHARS` | `100000` | Explicit extracted-text length guard; exceeding it fails without truncation |

The model receives complete extracted resume and job context with best-effort identity minimization. There is no silent input truncation or scoring formula. A context-window/schema incompatibility is a processing error. See [evaluation behavior](azure-openai.md).

## Resume storage and limits

| Variable | Default | Purpose |
| --- | --- | --- |
| `AZURE_STORAGE_CONNECTION_STRING` | Empty | Backend-only private Blob connection; required in connected mode |
| `AZURE_STORAGE_CONTAINER` | `resumes` | Existing private container; public access must be disabled |
| `LOCAL_RESUME_DIR` | `.local/resumes` | Demo-only private local directory relative to backend working directory |
| `MAX_RESUME_SIZE_MB` | `10` | PDF/DOCX upload limit, 1–25 MiB |
| `MAX_RESUME_UNCOMPRESSED_MB` | `40` | Maximum expanded DOCX archive size |

Supported formats are fixed to PDF and DOCX; an environment variable cannot enable unsupported extraction. The backend checks extension, MIME, actual contents, file integrity, PDF encryption/page bounds, and DOCX archive safety. Production storage rejects public containers and never uses local storage as a fallback. The application stores `azure:<generated-id>.pdf/.docx` references in SQLite portal metadata in the three-operation connected mode; demo uses `local:<generated-id>.pdf/.docx`. It does not store public URLs or document Base64 in F&O.

## Frontend

`VITE_APP_NAME` controls public branding/browser title at build time; its default is `TalentMatch AI`. API calls use same-origin `/api` and `/auth`; Vite's default proxy targets `http://127.0.0.1:8000`; for the user's trusted local HTTPS setup, set its `/api` and `/auth` target to `https://127.0.0.1:7242` in `frontend/vite.config.ts` and restart Vite with the mkcert CA trusted by Node. Nginx proxies in Compose. The frontend deliberately does not consume a cross-origin `VITE_API_BASE_URL`. There are no frontend integration secrets. Changing a backend secret never requires placing it in a `VITE_` variable.

## Required network destinations

Connected operation needs HTTPS access to the configured LinkedIn discovery/JWKS/token endpoints, `login.microsoftonline.com`, the configured D365 resource, the Azure OpenAI resource, and the selected `<account>.blob.core.windows.net` storage endpoint. Redis access is private TCP/TLS to the configured service. Install dependencies through their authorized package registries and preserve TLS/signature verification. Restrict network policy to actual configured hosts; this documentation does not replace an unknown existing allowlist.
