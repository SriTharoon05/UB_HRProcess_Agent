# TalentMatch AI — business reference

Document version: Phase 1 management handoff, 15 October 2026. Audience: HR leadership, business sponsors, ERP stakeholders, and project reviewers. The companion Word document is [Business Word document](reference/AI-Powered%20HR%20Recruitment%20Process%20Using%20D365-%20Business%20Document.docx).

## 1. Executive overview

TalentMatch AI brings published Dynamics 365 Finance & Operations job requirements into a recruitment portal and returns candidate/application information and supporting resume analysis to ERP. It reduces manual movement of information between a job posting, a candidate's document, and an HR review workspace.

This release is Phase 1. It supports recruitment intake and evidence-assisted review; it does not deliver the entire recruitment-to-employee lifecycle. Later phases are intended to extend screening, interviews, offers, onboarding, and employee maintenance across ERP and the portal.

AI helps reviewers locate documented experience against the selected job description. A score is contextual decision support. A person remains responsible for assessing suitability, verifying information, conducting interviews, and making employment decisions.

## 2. The business problem

Recruitment information often sits in separate systems: job requirements in ERP, candidate identities in external profiles, resumes in email or folders, and reviewer observations in spreadsheets. HR repeatedly copies details, searches long resumes, and checks whether an assessment belongs to the right requirement.

The Phase 1 portal links each application, resume, selected job description, AI result, and ERP acknowledgement with stable identifiers. Candidates see an application confirmation and business status. HR sees internal processing information and can recover a failed assessment without asking the candidate to submit again.

## 3. Delivered Phase 1 journey

| User | Action | Business result |
| --- | --- | --- |
| HR requirement owner | Creates/maintains an eligible job requirement in F&O | Portal presents the ERP-authored job context |
| Candidate | Opens a job and signs in with LinkedIn | Returns to that job application with permitted profile details |
| Candidate | Confirms contact details, uploads PDF/DOCX, accepts consent | One application is linked to the requirement and candidate |
| Portal/backend | Validates and acknowledges the ERP application | Candidate receives confirmation without waiting for AI |
| Background service | Extracts resume text and compares it with the selected JD | Structured assessment with supporting quotes and gaps |
| ERP integration | Saves the validated core evaluation and score | HR can use the evaluation alongside ERP business records |
| HR reviewer | Reviews job-specific candidates, evidence, and original resume | Human screening has traceable supporting information |
| HR operator | Retries a failed evaluation after its cause is corrected | Recovery reuses the existing application and cached valid result |

LinkedIn provides only approved identity/profile information. It does not guarantee a candidate's contact email or supply a full employment/skills history. The candidate completes missing basic details. A resume can contain incomplete or inaccurate claims; the system does not independently verify employment history.

## 4. Information ownership

| Location | Business information |
| --- | --- |
| Dynamics 365 F&O | Job requirements, candidate records, job applications, core match evaluations and application score |
| Portal metadata database | Frozen submitted job/contact context, consent, technical references, complete evidence and processing history |
| Private document storage | Original uploaded PDF/DOCX resumes |
| Redis/worker infrastructure | Sessions, queued work, locks and temporary coordination |

The existing ERP tables are `UBJobRequirementTable`, `UBCandidateTable`, `UBJobApplicationTable`, and `UBHRMatchEvaluationTable`. The project does not move ERP ownership into the browser. Optional Supabase PostgreSQL replaces local metadata persistence; it does not replace the ERP or automatically move original resume files.

## 5. How the AI result should be used

The analysis considers the complete readable resume against the selected requirement, including responsibilities, required/preferred skills, qualifications, certifications, experience context and supplied criteria. It can recognize documented project usage beyond a simple Skills list.

HR receives a 0–100 alignment score, an evidence label, a summary, reasoning, confidence, requirements with supporting quotes, partially supported areas, and requirements not evidenced. The backend checks that quoted evidence exists in the extracted document before accepting the assessment.

A strong score is not a hiring recommendation. A low score does not prove lack of ability, and an absent resume statement does not prove the candidate lacks the skill. Model reasoning can be wrong even when a quote is genuine. HR must consider context, verify relevant claims, and use appropriate human screening.

If the document cannot be read, configuration is missing, AI output cannot be validated, or ERP cannot save the result, no invented score is substituted. Internal failure information is available to HR/operations; it is not shown as candidate performance or rejection.

## 6. Expected value and success measures

| Expected value | Suggested measurement |
| --- | --- |
| Less manual re-entry | Time spent moving candidate/contact details into ERP |
| Faster first-pass evidence review | Median reviewer time per application compared with an agreed baseline |
| Traceable assessment | Percentage of displayed results with valid document evidence and ERP acknowledgement |
| More reliable application handoff | Duplicate applications, failed handoffs, and successful recovery rates |
| Better candidate continuity | Completion rate after selected-job LinkedIn sign-in |
| Operational visibility | Queue age, failure stage, time to recovery, and failed-save backlog |

These are proposed measures, not results already demonstrated. Establish a baseline and review them during an approved pilot. Include reviewer agreement, error rates, accessibility, and candidate fairness alongside efficiency.

## 7. Deployment and demonstration model

The application can run as a Docker Compose group on a local Windows/Linux/macOS Docker host. The web gateway, backend, background worker, and Redis start together. The browser URL is `https://localhost:7242`, preserving the configured LinkedIn callback.

After one-time image import, runtime configuration, and trusted certificate setup on each machine, the operator can start the existing application group using one Play action in Docker Desktop. A recipient needs the image archive and small runtime setup bundle, with authorized `.env` configuration; they do not need the source repository or developer tools.

Local hosting does not mean offline operation. LinkedIn, Dynamics 365, Azure OpenAI, private Azure Blob and optional Supabase require internet access and valid organizational permissions. Each machine must trust its own locally generated certificate authority. Secrets and CA signing keys must not be packaged into public images.

A shared cloud metadata database can make acknowledged records available to multiple configured backends. Concurrent connected workers must share queue/lock infrastructure and storage, or only one worker stack may be active. Sharing database credentials alone is not a complete shared-service deployment.

## 8. Responsibilities and governance

| Role | Responsibility |
| --- | --- |
| HR sponsor | Approves use cases, evaluation policy, pilot measures and human decision responsibility |
| Requirement owner | Maintains accurate JD, skills, criteria, dates, company and open status in ERP |
| HR reviewer | Reviews evidence, checks document context, records decisions through supported processes |
| ERP administrator | Deploys supported service contracts, permissions, company configuration and business defaults |
| Application operator | Protects runtime secrets, monitors API/worker, handles recovery and tested backups |
| Privacy/security owner | Approves provider/region processing, consent, retention, access and incident procedures |
| Development team | Maintains validation, integration behavior, accessible UI and phased enhancements |

The current HR login uses one environment-configured account. Broader enterprise use should move to named organizational access with suitable MFA/SSO, roles and audit attribution. Resume uploads need a reviewed document-security process; format validation does not replace malware scanning. Automated cross-system erasure and full lifecycle audit are not Phase 1 features.

## 9. Current boundaries and dependencies

- Job publication depends on ERP status/date criteria and the configured legal entity. A newly created record does not appear merely because it exists.
- Candidate history and HR lists show acknowledged portal applications; historic ERP applications and later ERP-only recruiter changes are not automatically synchronized.
- Text-based PDF/DOCX is supported. Scanned PDFs need a future OCR capability.
- Assessments depend on the actual model deployment, service availability, document clarity, and complete job requirements.
- Original documents, metadata, ERP records, queues and backups have separate retention responsibilities.
- SQLite is intended for one host/shared local volume. Supabase/PostgreSQL provides shared metadata, with additional coordination required for multiple active stacks.
- Docker deployment tooling does not establish organizational production approval, a service-level guarantee, or live provider acceptance.

## 10. Roadmap beyond Phase 1

| Phase | Proposed business scope | Key design/approval work |
| --- | --- | --- |
| Phase 1 — delivered scope | Job publication, candidate intake, evidence comparison, HR review and recovery | Validate pilot, ERP handoff, provider configuration and operations |
| Phase 2 — planned | Human screening outcomes, assignments, notes and approvals | Supported ERP status updates, permissions and decision audit |
| Phase 3 — planned | Interviews, panel scheduling, feedback, offers and approvals | Calendar/communication contracts, panel privacy, approval ownership |
| Phase 4 — planned | Preboarding, document collection, onboarding checklists and employee creation | Identity transition, document policy, ERP onboarding mapping |
| Phase 5 — planned | Ongoing employee information and supported HR self-service | Field ownership, update approvals, access separation and retention |

ERP remains the business system of record. React provides candidate/HR interaction, while FastAPI coordinates integrations and appropriate AI capabilities. Future functions are not included simply because they appear in this roadmap; each phase needs its own requirements, contracts, acceptance criteria and release authorization.

## 11. Pilot acceptance and handoff

A controlled pilot should demonstrate an eligible ERP job, selected-job sign-in, complete confirmed application, private document access, a supported resume/JD evaluation, and a matching ERP evaluation record. HR should inspect both evidence and original document, recover a controlled failure, and verify that candidate pages do not reveal internal diagnostics.

The operational handoff should name the service owner, support route, environment/secret owner, database/document backup policy, retention owner, and provider cost/budget limits. Use synthetic sample data for demonstrations unless real candidate processing has been approved.

Refer to the technical reference, Docker guide and Supabase migration guide for implementation instructions. The project's validation record describes executed checks; this business document does not certify external systems or guarantee an individual model result.
