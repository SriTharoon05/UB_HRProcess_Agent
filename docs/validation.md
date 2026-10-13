# Validation performed

| Check | Result |
| --- | --- |
| `scripts/install.sh` | Locked uv installation and clean `npm ci` passed using writable local caches |
| Backend pytest | 202 passed, including 8 tests against a real Redis instance |
| LinkedIn and Entra authentication regressions | 123 passed, including state-bound job return, redirect attacks, standard profile fields, invalid member-ID email, optional contacts, token validation, strict Entra nonce checks, and safe diagnostics |
| Backend Ruff | Passed |
| Frontend Vitest | 68 passed across 4 test files |
| Frontend ESLint and TypeScript | Passed |
| Vite production build | Passed; candidate and HR screens load in separate chunks |
| Backend and frontend Docker builds | Passed; Python 3.12 and Node 22 build environments |
| Demo browser smoke | Passed against the development server and built API/nginx containers |
| Selected-job LinkedIn browser flow | Passed with real Authlib state handling and RSA ID-token validation; provider network responses mocked, three 303 callbacks restored selected-job/form/query/fragment |
| Visual checks | Desktop 1440px and mobile 390px; navigation works and tables scroll within their containers |
| Saved startup commands | Services stopped and restarted successfully through `scripts/dev.sh` |

The browser scenario submits a newly generated PDF through the candidate application form, verifies its entered contact name/email, current application identifier and candidate history, checks candidate-to-HR access denial, switches to HR, opens the evaluation, and downloads the exact original PDF. It also checks mobile layout and browser exceptions. Sample evaluations remain labeled fictional fixtures. The contact-field regression was rerun against the development services; container smoke checks were performed during the initial build.

The selected-job browser check uses isolated test services and a fictional LinkedIn identity. It exercises the complete signed callback, profile summary, empty email when a member URN is returned, manual contact entry, real PDF upload, consent, candidate-owned history, and HR denial. Desktop 1440px and mobile 390px checks found no page overflow or browser exceptions. [Desktop](screenshots/linkedin-profile-desktop.png) and [mobile](screenshots/linkedin-profile-mobile.png) screenshots use fictional data; this does not establish a live LinkedIn/D365/AI deployment.

Backend tests validate signed OIDC tokens, state/nonce/issuer/audience/expiry handling, roles, CSRF, ownership, session revocation races, upload validation, real document extraction, D365 mappings, AI output/evidence validation, and durable queue recovery. External D365, identity-provider, Azure OpenAI, and Blob calls are mocked. Real Redis tests verify queue retention, recovery, cached evaluation retries, idempotency, and session updates.

## External integration status

No live D365, LinkedIn, Entra, Azure OpenAI, or Azure Blob credentials were provided during this build. Their adapters are implemented and tested with mocks; live provider behavior and deployment permissions remain unverified.

The existing D365 `getOpenRequirements` and `submitApplication` paths are configured from the supplied requirements. Their actual X++ request/response contracts still need confirmation. `saveCandidateEvaluation` and `getTopCandidates` need X++ deployment; their example paths intentionally remain empty. Candidate-owned history and details need additional read contracts with ownership fields. Persistent processing/failure updates and business-record deletion need separate D365 capabilities.

GitHub Actions is configured to run tests/builds and the demo browser scenario. Local passing checks do not establish the outcome of a future Actions run, a production deployment, or restoration in a new cloud task.
