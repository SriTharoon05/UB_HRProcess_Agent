# Validation performed

| Check | Result |
| --- | --- |
| `scripts/install.sh` | Locked uv installation and clean `npm ci` passed using writable local caches |
| Backend pytest | 57 passed, including 6 tests against a real Redis instance |
| Backend Ruff | Passed |
| Frontend Vitest | 39 passed across 4 test files |
| Frontend ESLint and TypeScript | Passed |
| Vite production build | Passed; candidate and HR screens load in separate chunks |
| Backend and frontend Docker builds | Passed; Python 3.12 and Node 22 build environments |
| Demo browser smoke | Passed against the development server and built API/nginx containers |
| Visual checks | Desktop 1440px and mobile 390px; navigation works and tables scroll within their containers |
| Saved startup commands | Services stopped and restarted successfully through `scripts/dev.sh` |

The browser scenario submits a newly generated PDF through the candidate application form, verifies its current application identifier and candidate history, checks candidate-to-HR access denial, switches to HR, opens the evaluation, and downloads the exact original PDF. It also checks mobile layout and browser exceptions. Sample evaluations remain labeled fictional fixtures.

Backend tests validate signed OIDC tokens, state/nonce/issuer/audience/expiry handling, roles, CSRF, ownership, session revocation races, upload validation, real document extraction, D365 mappings, AI output/evidence validation, and durable queue recovery. External D365, identity-provider, Azure OpenAI, and Blob calls are mocked. Real Redis tests verify queue retention, recovery, cached evaluation retries, idempotency, and session updates.

## External integration status

No live D365, LinkedIn, Entra, Azure OpenAI, or Azure Blob credentials were provided during this build. Their adapters are implemented and tested with mocks; live provider behavior and deployment permissions remain unverified.

The existing D365 `getOpenRequirements` and `submitApplication` paths are configured from the supplied requirements. Their actual X++ request/response contracts still need confirmation. `saveCandidateEvaluation` and `getTopCandidates` need X++ deployment; their example paths intentionally remain empty. Candidate-owned history and details need additional read contracts with ownership fields. Persistent processing/failure updates and business-record deletion need separate D365 capabilities.

GitHub Actions is configured to run tests/builds and the demo browser scenario. Local passing checks do not establish the outcome of a future Actions run, a production deployment, or restoration in a new cloud task.
