# TalentMatch AI — technical reference

Document version: Phase 1 deployment handoff, 15 October 2026. Audience: developers, ERP administrators, infrastructure operators, and technical reviewers. The companion Word document is [Technical Word document](reference/AI-Powered%20HR%20Recruitment%20Process%20Using%20D365%20-%20Technical%20Document.docx).

## 1. Scope and implementation status

TalentMatch AI connects a React recruitment portal to Dynamics 365 Finance & Operations (F&O) through FastAPI. Phase 1 covers published job discovery, LinkedIn candidate sign-in, confirmed candidate contact details, private resume submission, AI-assisted resume/JD evidence comparison, and an authenticated HR review workspace. The ERP remains the source of job requirements and core recruitment records.

The current release is a Phase 1 application with deployment tooling and operational controls. It is not the complete employee lifecycle product. Screening workflows, interview scheduling, offers, onboarding, and employee maintenance are planned phases. No AI score automatically hires or rejects a person.

| Capability | Current implementation |
| --- | --- |
| Job publication | Reads open requirements from the existing F&O custom service |
| Candidate identity | LinkedIn OIDC; permitted profile details displayed; missing contacts collected |
| Job return after sign-in | State-bound return to the selected application route |
| Applications | PDF/DOCX validation, consent, stable application identifiers, ERP acknowledgement |
| AI evidence | Full readable resume vs selected frozen JD; structured validation and bounded correction |
| HR review | Username/password session, job-specific candidate list, evidence, private resume access |
| Failed evaluation recovery | HR retry and refresh; cached valid AI result reused for save-only retries |
| Portal metadata | SQLite by default; optional PostgreSQL/Supabase adapter and explicit migration |
| Local packaging | HTTPS localhost Docker Compose group with gateway, API, worker, and Redis |
| Azure packaging | Separate ACR/App Service single-container image, Supervisor, public same-origin HTTPS, OIDC-gated company GitHub CI/CD |
| Future lifecycle | Screening, interviews, offers, onboarding, and employee maintenance remain roadmap |

## 2. System architecture

A same-origin HTTPS gateway serves the built React assets and forwards `/api` and `/auth` to FastAPI. Docker publishes only `127.0.0.1:7242`. The browser opens `https://localhost:7242`; the registered LinkedIn callback remains `https://localhost:7242/auth/linkedin/callback`. The backend listens on HTTP port 8000 inside the Docker network. Internal HTTP does not change the browser-visible callback.

That description applies to the local Compose package. The separate Azure image uses App Service's public HTTPS termination, Nginx on internal port 8080, and the final public hostname for its LinkedIn callback. It packages API, ARQ and Redis under Supervisor; durable metadata is PostgreSQL and resumes stay in private Blob. See [Azure hosting and company CI/CD](azure-app-service.md) and [the IT request](azure-it-request.md). Its GitHub workflow is explicitly gated and does not publish to a company account automatically.

| Component | Responsibility | Persistence or external dependency |
| --- | --- | --- |
| React web gateway | Browser UI, SPA fallback, HTTPS termination, same-origin API proxy | Built frontend assets and per-machine server certificate |
| FastAPI API | Authentication, authorization, upload validation, ERP calls, metadata reads | Shared metadata database, Redis, private Blob |
| Evaluation worker | Extraction, AI validation, retries, ERP evaluation delivery, outbox recovery | Same backend configuration as API |
| Redis | Server-side sessions, queues, locks, temporary processing coordination | Persistent local Docker volume or shared private managed service |
| Metadata store | Frozen application/JD snapshots, acknowledgement, complete AI output | SQLite named volume or PostgreSQL/Supabase |
| F&O custom services | Job reads, core application write, core evaluation write | Existing F&O model and four tables |
| Azure Blob | Private original PDF/DOCX document bytes in connected mode | Existing private container |
| Azure OpenAI | Structured contextual job/resume evidence assessment | Configured deployment, key, API version |
| LinkedIn | OIDC identity and approved standard profile claims | Registered application and exact redirect URI |

A Docker image contains application binaries and dependencies. It does not contain live `.env` values, production records, trusted host certificates, or local Docker volumes. A portable image archive therefore distributes the application, while runtime configuration and data migration remain separate steps.

## 3. Candidate-to-ERP processing flow

1. HR creates a requirement in `UBJobRequirementTable`. The configured F&O service returns rows meeting its open-status and date criteria in the integration user's company.
2. A candidate opens a specific requirement and signs in with LinkedIn. The backend binds the selected return route to OAuth state. The callback validates the provider response and returns to the same application context.
3. The portal displays the permitted LinkedIn profile information. Name/email may be absent; the candidate confirms a full name and valid contact email and may add a phone/profile URL. A provider member identifier is not an email address.
4. FastAPI validates session ownership, CSRF, current consent version, job availability, PDF/DOCX contents and size. It stores the original document privately and computes a checksum.
5. The metadata store freezes confirmed contact and identity, job context, consent, document reference/checksum, request fingerprint, and one stable `ApplicationId` before ERP submission.
6. `submitApplication` creates or reuses the candidate and linked application in one ERP transaction. The backend checks the acknowledgement and then queues background evaluation. Candidate confirmation does not wait for the LLM.
7. The worker retrieves the private file, checks its checksum, and extracts readable text. It sends complete permitted resume text and complete frozen job context to Azure OpenAI, with best-effort identity minimization.
8. Structured response and evidence checks run. A bounded correction loop asks the model to repair invalid output. Unsupported output never becomes a fabricated fallback score.
9. The complete validated evaluation is durably cached before `saveCandidateEvaluation`. A stable `EvaluationId` permits idempotent ERP delivery. ERP saves the evaluation and application score/status transactionally.
10. Completion is exposed to HR only after a matching ERP acknowledgement. Save retries reuse cached AI output. Candidate pages show business application status and do not expose internal AI failure states or assessment details.

The application is not one distributed transaction across Blob, metadata, Redis, Azure OpenAI, and F&O. Durable outbox records, stable identifiers, ERP uniqueness/upsert rules, and recovery coordinate these boundaries.

## 4. Data ownership and table mapping

| F&O table | Business purpose | Selected Phase 1 integration fields |
| --- | --- | --- |
| `UBJobRequirementTable` | HR-authored requirement and complete JD | `RequirementId`, `JobTitle`, `JobDescription`, `Responsibilities`, `RequiredSkills`, `PreferredSkills`, `RequiredQualifications`, `RequiredCertifications`, `Department`, `JobLocation`, `WorkMode`, `EmploymentType`, experience bounds, openings, status and dates, criteria/rubric |
| `UBCandidateTable` | Candidate and stable verified identity | `CandidateId`, `FirstName`, `LastName`, `Email`, `Phone`, `LinkedInProfileUrl`, `LinkedInIssuer`, `LinkedInSub`, `IdentityKey` |
| `UBJobApplicationTable` | Candidate-to-requirement application | `ApplicationId`, `CandidateId`, `RequirementId`, existing default business status, `OverallScore`, `AIStatus` |
| `UBHRMatchEvaluationTable` | Core evaluation for HR/ERP | `EvaluationId`, `ApplicationId`, `RequirementId`, `Score`, `MeetsMinimumCriteria`, `MatchLabel`, `Summary`, `MatchedSkillsJson`, `MissingSkillsJson`, `EvidenceJson` |

`Summary`, `MatchedSkillsJson`, `MissingSkillsJson`, and `EvidenceJson` are Memo fields in the user's F&O deployment. The deployed service must accept those text fields without applying a short-string limit. Existing ID lengths, enums, indexes, and table validation must match the deployed contract; this packaging task does not modify ERP metadata.

The metadata database stores private document references/hashes, consent, technical timestamps, frozen identity/contact/JD snapshots, submission keys/outbox state, full evidence and model/prompt/rubric provenance. No additional ERP columns are required for these technical values. In PostgreSQL the application uses the dedicated `talentmatch` schema; metadata tables are not a public browser API.

Actual document bytes remain in private Azure Blob for connected mode. Supabase PostgreSQL is metadata storage; it is not an automatic replacement for Azure Blob, Redis, or F&O. Redis is not the only durable copy of acknowledged applications/evaluations.

## 5. ERP service contract

The integration invokes JSON POST operations under:

`/api/services/UBHRPortalServiceGroup/UBHRPortalService/`

| Operation | Request | Acknowledgement |
| --- | --- | --- |
| `getOpenRequirements` | `{}`; integration user's current company | `Requirements` array containing complete eligible job context |
| `submitApplication` | `_request` with company, stable application ID, requirement, confirmed contacts and verified provider identity | Boolean `Success`, matching `ApplicationId`, stable `CandidateId` |
| `saveCandidateEvaluation` | `_request` with company, stable evaluation/application/requirement IDs and selected score/evidence | Boolean `Success` and matching application/evaluation identifiers |

`D365_CONTRACT_MODE=sqlite` names the lean three-operation ERP contract; it remains the correct value when `METADATA_BACKEND=postgres`. The name is retained for compatibility. The three optional legacy read paths stay empty. The frontend never calls the ERP service directly or receives service credentials.

Candidate history and HR lists cover acknowledged portal submissions in the metadata store. They do not import all pre-existing ERP applications or automatically synchronize recruiter status changes made directly in F&O. A separate supported synchronization capability is future work.

See [D365 endpoints](d365-endpoints.md), [schema](d365-schema.md), and the [Visual Studio source-pack guide](../d365/README.md).

## 6. AI assessment and document limits

The worker supports readable PDF and DOCX files. It validates actual file structure, configured size, checksum, and extraction. Image-only/scanned PDF content requires an OCR capability that is not implemented here. Password-protected, corrupt, empty, unsupported, or excessively large inputs fail explicitly.

Azure OpenAI receives the complete job context and readable resume within configured guards. The score is a model-generated contextual estimate from 0–100, with justification, confidence, matched/partial/not-evidenced requirements, and quoted evidence. There is no fixed keyword-weight formula and no score-based hiring decision.

Evidence must be a contiguous source quote in both the original extracted text and the minimized text sent to the model. Whitespace differences caused by layout are allowed; changed words, punctuation, numbers, invented projects, combined passages, and unsupported paraphrases are rejected. A positive score requires supporting evidence. A genuinely weak or zero-evidence match is a valid assessment.

`AZURE_OPENAI_VALIDATION_ATTEMPTS` bounds schema/evidence correction to a maximum of three requests. Temporary network/provider failures have separate bounded worker retries. The AI validation operation has a 360-second total budget within the worker job limit; timeout/cancellation leaves an actionable internal failure state instead of an indefinitely processing record. A validation failure is visible to HR; a cached valid result followed by an ERP failure retries persistence without calling AI again.

Quotes establish traceability, not factual truth or objective model accuracy. HR must verify relevance, claims, bias, and missing context. Best-effort identity minimization does not guarantee anonymization. The system prompt treats resume/JD contents as data, including test instructions embedded in sample documents.

## 7. Identity, access, and configuration

Candidate identity comes from validated LinkedIn issuer/subject, not editable contact data. OAuth state and selected return routes are validated server-side. Only approved standard claims are displayed; LinkedIn sign-in does not supply a full career history, phone number, skills inventory, or guaranteed contact email.

HR currently signs in using one backend-configured username/password account. Values default empty, matching is exact, attempts are rate limited, successful login rotates session/CSRF, and HR role checks run on the server. A shared configuration account is suitable for the current controlled handoff; named users, MFA, organization SSO, least-privilege HR permissions, and audit attribution are enhancements needed before broader enterprise rollout.

Browser sessions use an opaque cookie and server-side state. Mutations require CSRF protection. Candidate-owned reads and HR resume downloads are authorized in FastAPI. Candidate API responses omit internal evaluation/processing details.

Secrets exist only in the runtime `.env`/secret store. Never include `.env` or certificates in exported images, Git, frontend `VITE_` variables, screenshots, or shared documents. Credentials and model prompts/resume contents are excluded from operational logs. Protect Docker host access: administrators can inspect container environment values.

## 8. Local Docker handoff

The Compose application contains `web`, `api`, `worker`, and `redis`. The portal and LinkedIn callback use HTTPS localhost port 7242. After initial image import, configuration, and unique certificate trust, Docker Desktop's Play action on the `talentmatch` application group starts the existing containers. A first-time arbitrary `docker run` on one image cannot create and configure the complete stack.

Distribute the exported image archive and tiny runtime bundle; no source code, Node.js, Python, Visual Studio, or Git is needed on the recipient system. Docker Desktop must support Linux containers. The recipient supplies authorized `.env` values and runs setup once. A local trusted CA/server certificate must be generated for each machine; never transfer a signing private key or bypass TLS validation.

The Docker-only prerequisite refers to application runtimes. Internet and valid credentials remain necessary for LinkedIn, F&O, Azure OpenAI, Azure Blob, and Supabase. Only the local browser/server entry point is localhost; these integrations are external services.

See [Docker setup and image transfer](docker-local.md) for exact export/import, startup, certificate, backup, and troubleshooting commands.

## 9. PostgreSQL/Supabase migration and shared access

Set `METADATA_BACKEND=postgres`, a private `DATABASE_URL`, and verified TLS settings after migrating existing SQLite metadata. `D365_CONTRACT_MODE=sqlite` remains unchanged. The backend uses a direct PostgreSQL driver; a Supabase browser URL, anonymous key, or service-role API key is not used by this adapter.

Create a Supabase project, choose an approved region, copy its actual database connection string, and prefer a session pooler on port 5432 when direct database IPv6 routing is unavailable. Copy the displayed host and username; do not guess the project-specific pooler hostname. URL-encode special characters in the password. TLS defaults to `verify-full`; provide `DATABASE_SSLROOTCERT` when the server chain requires an explicit CA.

Stop writers, take a consistent backup, dry-run the import, import transactionally, switch backend selection, and restart API/worker with identical settings. The migration preserves original IDs and source SQLite, rejects conflicts, and permits identical reruns. See [Supabase migration](supabase.md).

Sharing only the database does not coordinate queues across machines. Use one active connected worker stack per metadata database, or configure all participating API/worker stacks with the same private Redis endpoint, `REDIS_PREFIX`, company, and Blob container. Independent per-PC Redis instances with a shared metadata database are not a supported simultaneous-worker setup. Database evaluation advisory locks additionally protect duplicate model processing across workers; shared Redis remains recommended for complete queue/session coordination. Redis sessions remain environment-specific unless deliberately shared with a consistent trust/configuration policy.

## 10. Operations, recovery, and backup

Use Docker Desktop service logs or Compose logs for API and worker. Trace stable application ID across extraction, model validation, durable cache, ERP request, and acknowledgement. Request IDs identify browser operations; D365 correlation/activity identifiers connect upstream failures. Health checks confirm local process readiness, not every external permission or service contract.

HR can refresh a list or retry a failed evaluation after fixing its cause. Retry does not submit a duplicate application. Queue/active/completed guards prevent normal repeated clicks from starting unnecessary work, and cached valid AI output is reused. Stable ERP identifiers and uniqueness/upsert constraints are still required for timeouts after an ERP commit.

Back up the metadata store, private Blob documents, environment configuration through approved secret management, and any required Redis persistence separately. A Docker image archive is not a data backup. SQLite requires its online backup API or stopped writers; copying only a live main file while WAL is active is unsafe. PostgreSQL/Supabase requires managed backups or `pg_dump`/restore under a tested policy. Keep source SQLite until migration/restore and ERP/document references are reconciled.

`RETENTION_DAYS` controls temporary processing/idempotency state. It does not automatically erase metadata, Blob documents, F&O records, exported documents, or backups. Cross-system retention, anonymization, subject requests, and deletion remain operator/business policy work.

## 11. Verification and rollout boundary

Repository tests and browser screenshots verify local code, mock integration contracts, responsive rendering, and container behavior where executed. Live D365 compilation/security, provider registration, network permissions, approved secrets, model capacity, and real service acknowledgements require environment-specific acceptance. Consult the current [validation record](validation.md) for checks actually performed.

A rollout should prove selected-job LinkedIn return, one real synthetic application, duplicate submission safety, extracted PDF/DOCX evidence, acknowledged ERP evaluation, HR retry after a controlled failure, private resume authorization, and restored metadata/document linkage. Production readiness is an operational gate, not a claim created by a Dockerfile.

Remaining enterprise capabilities include organization-managed HR identity, malware scanning/quarantine when required, OCR, cross-system erasure, durable audit attribution, centralized operations, approved backup/recovery objectives, live status synchronization, and load/capacity validation.

## 12. Planned lifecycle phases

| Phase | Intended scope | ERP and portal ownership |
| --- | --- | --- |
| Phase 1 — current | Requirement publication, candidate intake, private resume, evidence comparison, HR review/retry | F&O business records; React workflow; FastAPI integration/AI |
| Phase 2 — planned | Recruiter screening decisions, reviewer assignment, screening notes and approvals | Supported F&O statuses/contracts and portal review actions |
| Phase 3 — planned | Interview scheduling, panels, feedback, approvals and offers | F&O lifecycle records with portal interaction/integrations |
| Phase 4 — planned | Preboarding, document/checklist collection, approvals and employee creation | F&O onboarding/HR records; portal self-service |
| Phase 5 — planned | Employee maintenance and supported HR lifecycle services | ERP system of record with governed React/FastAPI capabilities |

Each future phase needs its own data contracts, access model, human approvals, audit/retention design, acceptance criteria, and release review. Dates, budgets, and delivered integrations are not implied by this roadmap.
