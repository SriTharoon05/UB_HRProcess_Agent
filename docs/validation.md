# Phase 1 verification record

This record distinguishes executed local checks from external integration acceptance. Verification used fictional resumes and identities; no live candidate data was uploaded to a provider.

| Check | Result |
| --- | --- |
| Complete backend suite | **338 passed**, including real Redis, local PostgreSQL integration tests and the Azure runtime checks; no tests skipped in the latest complete run |
| PostgreSQL / migration checks | Shared SQLite/PostgreSQL storage contract, concurrent reservation, company/owner scope, immutable snapshots, private RLS schema, cross-process evaluation locks, cancellation cleanup, source-only dry run, idempotent import, unchanged source and atomic conflict rollback passed |
| PostgreSQL evaluation workflow | Real PostgreSQL with controlled AI/D365 responses: acknowledged submission, validated result caching, failed save, retry and matching completion passed |
| Frontend suite | **73 passed**, including HR retry/refresh and candidate processing-status privacy |
| Static checks and build | Backend Ruff, frontend ESLint, TypeScript and Vite production build passed |
| ERP source bundle | Field references, five DTOs, six fixtures, three actual mocked adapter calls, SQLite reopen and Postman routes passed |
| Runtime image builds | Backend and HTTPS frontend/gateway built successfully; final backend image file hashes match the final application sources |
| Source-free transfer | Exported approximately 440 MB image archive; checksum, import, image platform, Word documents and absence of source, credentials, certificates and private data checked |
| Local HTTPS | Generated machine-specific certificate verified against its CA and localhost hostname; only host port 127.0.0.1:7242 published |
| Production container mode | Redis, API, worker and web healthy; HTTPS health, secure HttpOnly session cookies, CSRF HR login, SPA deep routes and security headers checked |
| Container browser workflow | Built HTTPS gateway: job listing, candidate demo sign-in, generated PDF upload, entered contact details, owned history, HR authorization/password login, evidence display, exact private resume download, mobile navigation and no browser exceptions passed |
| Restart behavior | Stopped and restarted the existing four production containers, including starting gateway/worker before dependencies; API HTTPS request succeeded and all services returned healthy |
| Visual review | Eleven desktop/mobile route screenshots inspected at 1440 px and 390 px; no page overflow or JavaScript exceptions; heading, mobile hero and text readability defects corrected |
| Word documents | Both DOCX archives reopened; document XML, headings, tables, links and two embedded fictional screenshots per document checked |
| Documentation | Relative Markdown links, shell syntax, generator lint and whitespace checks passed |

## Azure single-container verification

The separate `Dockerfile.azure` image built successfully for Linux/amd64. Its Nginx, FastAPI, ARQ and Redis processes were checked together. The fictional browser workflow passed through the built image: job browsing, candidate sign-in, PDF submission, owned history, HR login, evidence and private resume download, including mobile navigation without browser exceptions.

Production-mode checks used a real local PostgreSQL server with certificate-verified TLS. Readiness verified the API, Redis and worker heartbeat. A simulated App Service HTTPS edge checked secure HttpOnly cookies, CSRF-protected HR login, role boundaries and SPA deep links. The final image runs as UID 10001; application code is not writable by that user and application-settings JSON is absent from the image.

The 13 Azure runtime tests passed within the complete backend suite. Ruff, TypeScript/Vite image build, workflow YAML parsing and workflow shell syntax checks passed. Markdown-derived Word drafts were generated and their package structure checked. On synchronizing with the remote repository, the user-edited, renamed Word documents were preserved unchanged and documentation/export links were updated to those maintained files. A first full-suite attempt exhausted this workspace's build-cache disk space; after removing regenerable Docker build cache, the complete run passed with **338 tests**.

No company GitHub push, company workflow execution, Azure provisioning or live Azure deployment was performed. App Service TLS termination and managed identity, registry image pulls, company network access, Key Vault references, live model output and the final LinkedIn callback require acceptance in the provisioned Azure environment. Local edge simulation does not replace those checks.

## Verification boundaries

The production-mode local container checks do not call live LinkedIn, D365, Azure OpenAI, Azure Blob or Supabase. Provider calls in automated workflows are controlled responses, while Redis and PostgreSQL persistence are real. The user has separately reported their native connected Phase 1 flow working; this does not replace acceptance testing of a new container deployment with its actual authorized settings.

The browser container smoke uses the explicit fictional demo override. HTTPS requests verify the generated local CA; Chromium is restricted to the generated leaf public-key pin for this isolated check. No global TLS verification was disabled. A recipient must install their own machine-local trust using setup before using LinkedIn.

Docker builds and runtime verification executed on Linux/amd64. Windows PowerShell and macOS trust steps are provided and reviewed but were not executed on those operating systems. Linux group stop/start was tested; Docker Desktop's graphical button itself was not available in this environment. After initial setup creates the Compose group, that group is the unit to start.

No LibreOffice/Word renderer was installed; DOCX package structure and content were checked, but rendered pagination was not verified. X++ compilation, AOT field/index compatibility, database synchronization and deployment still require an F&O development environment. The repository now includes the four confirmed Memo-field validation correction supplied in chat.

Current application history and ranking reflect acknowledged portal metadata snapshots; they do not automatically synchronize all historic ERP records or subsequent ERP-only recruiter status changes. Database migration does not move Blob bytes, Redis sessions or ERP data. Shared PostgreSQL has an additional evaluation lock, but an initial multi-machine rollout should still use one active stack or explicitly shared Redis/prefix and Blob configuration.

These checks support a Phase 1 rollout candidate. They do not establish high availability, an independent security audit, fairness certification, enterprise identity lifecycle, complete retention/erasure automation or future interview/onboarding functionality. Use the documented acceptance checklist with real authorized integrations before wider production rollout.
