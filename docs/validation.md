# Phase 1 verification record

This record distinguishes executed local checks from external integration acceptance. Verification used fictional resumes and identities; no live candidate data was uploaded to a provider.

| Check | Result |
| --- | --- |
| Complete backend suite | **325 passed**, including real Redis and local PostgreSQL integration tests; no tests skipped in the complete run |
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

## Verification boundaries

The production-mode local container checks do not call live LinkedIn, D365, Azure OpenAI, Azure Blob or Supabase. Provider calls in automated workflows are controlled responses, while Redis and PostgreSQL persistence are real. The user has separately reported their native connected Phase 1 flow working; this does not replace acceptance testing of a new container deployment with its actual authorized settings.

The browser container smoke uses the explicit fictional demo override. HTTPS requests verify the generated local CA; Chromium is restricted to the generated leaf public-key pin for this isolated check. No global TLS verification was disabled. A recipient must install their own machine-local trust using setup before using LinkedIn.

Docker builds and runtime verification executed on Linux/amd64. Windows PowerShell and macOS trust steps are provided and reviewed but were not executed on those operating systems. Linux group stop/start was tested; Docker Desktop's graphical button itself was not available in this environment. After initial setup creates the Compose group, that group is the unit to start.

No LibreOffice/Word renderer was installed; DOCX package structure and content were checked, but rendered pagination was not verified. X++ compilation, AOT field/index compatibility, database synchronization and deployment still require an F&O development environment. The repository now includes the four confirmed Memo-field validation correction supplied in chat.

Current application history and ranking reflect acknowledged portal metadata snapshots; they do not automatically synchronize all historic ERP records or subsequent ERP-only recruiter status changes. Database migration does not move Blob bytes, Redis sessions or ERP data. Shared PostgreSQL has an additional evaluation lock, but an initial multi-machine rollout should still use one active stack or explicitly shared Redis/prefix and Blob configuration.

These checks support a Phase 1 rollout candidate. They do not establish high availability, an independent security audit, fairness certification, enterprise identity lifecycle, complete retention/erasure automation or future interview/onboarding functionality. Use the documented acceptance checklist with real authorized integrations before wider production rollout.
