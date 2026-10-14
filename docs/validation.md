# Validation performed

The current screenshot-table/SQLite revision passed the complete repository checks. Browser checks below remain the previously executed demo/authentication scenarios; they do not establish live F&O behavior. X++ build and live F&O acceptance require the development environment.

| Check | Result |
| --- | --- |
| `scripts/install.sh` | Locked uv installation and clean `npm ci` passed using writable local caches |
| Backend pytest | 212 passed, including 10 SQLite recovery/integration tests and 8 tests against a real Redis instance |
| LinkedIn and Entra authentication regressions | 123 passed, including state-bound job return, redirect attacks, standard profile fields, invalid member-ID email, optional contacts, token validation, strict Entra nonce checks, and safe diagnostics |
| Backend Ruff | Passed |
| Frontend Vitest | 68 passed across 4 test files |
| Frontend ESLint and TypeScript | Passed |
| Vite production build | Passed; candidate and HR screens load in separate chunks |
| Backend and frontend Docker builds | Revised Python 3.12 backend build passed; frontend Docker build passed during the baseline validation |
| Shared container SQLite persistence | Passed: UID 10001 initialized the database and a fresh non-root container read the same persistent volume |
| Demo browser smoke | Passed against the development server and built API/nginx containers |
| Selected-job LinkedIn browser flow | Passed with real Authlib state handling and RSA ID-token validation; provider network responses mocked, three 303 callbacks restored selected-job/form/query/fragment |
| Visual checks | Desktop 1440px and mobile 390px; navigation works and tables scroll within their containers |
| Saved startup commands | Services stopped and restarted successfully through `scripts/dev.sh` |
| Current three-operation D365/SQLite bundle | Passed: exact screenshot field references, five DTOs, six fixtures, three actual mocked adapter calls, SQLite restart and Postman routes |
| Legacy D365 adapter regression | 13 passed in the current complete test run; legacy adapter retained |
| X++ build/database synchronization | Not executed; requires an F&O development environment |

The user's subsequent Visual Studio build reported combined locking hints and a reserved `index` local in the portal class. Both are corrected in the source. Targeted guards passed four valid and four invalid syntax-pattern cases; bundle checks and the 23 SQLite/legacy D365 adapter tests passed after the correction. [build-errors.md](../d365/build-errors.md) maps the stale field references in the user's existing application service/form. Those external AOT objects are not in this repository; their bindings must be changed in Visual Studio. The revised class still requires an actual F&O build.

The browser scenario submits a newly generated PDF through the candidate application form, verifies its entered contact name/email, current application identifier and candidate history, checks candidate-to-HR access denial, switches to HR, opens the evaluation, and downloads the exact original PDF. It also checks mobile layout and browser exceptions. Sample evaluations remain labeled fictional fixtures. The contact-field regression was rerun against the development services; container smoke checks were performed during the initial build.

The selected-job browser check uses isolated test services and a fictional LinkedIn identity. It exercises the complete signed callback, profile summary, empty email when a member URN is returned, manual contact entry, real PDF upload, consent, candidate-owned history, and HR denial. Desktop 1440px and mobile 390px checks found no page overflow or browser exceptions. [Desktop](screenshots/linkedin-profile-desktop.png) and [mobile](screenshots/linkedin-profile-mobile.png) screenshots use fictional data; this does not establish a live LinkedIn/D365/AI deployment.

Backend tests validate signed OIDC tokens, state/nonce/issuer/audience/expiry handling, roles, CSRF, ownership, session revocation races, upload validation, real document extraction, D365 mappings, AI output/evidence validation, and durable queue recovery. External D365, identity-provider, Azure OpenAI, and Blob calls are mocked. Real Redis tests verify queue retention, recovery, cached evaluation retries, idempotency, and session updates.

## External integration status

No live D365, LinkedIn, Entra, Azure OpenAI, or Azure Blob credentials were provided during this build. Their adapters are implemented and tested with mocks; live provider behavior and deployment permissions remain unverified.

The current [D365 source bundle](../d365/README.md) provides five contracts and `UBHRPortalService` for exactly three operations under `UBHRPortalServiceGroup/UBHRPortalService`. It uses the four existing screenshot tables in model `UBHR_Nive` and proposes no new tables/columns/EDTs/enums. The default `sqlite` adapter stores complete portal metadata and validated evaluations locally; F&O stores the selected core business values.

X++ compilation, existing EDT/enum compatibility, database synchronization for any index/EDT changes, live serializer/security acceptance and deployment remain unexecuted. The documented default endpoint paths are source-pack paths, not verified deployed services. History/ranking are local acknowledged snapshots and do not establish live F&O recruiter-status synchronization. The SQLite file must be shared durably by API and worker, with tested backup/restore.

GitHub Actions is configured to run tests/builds and the demo browser scenario. Local passing checks do not establish the outcome of a future Actions run, a production deployment, or restoration in a new cloud task.
