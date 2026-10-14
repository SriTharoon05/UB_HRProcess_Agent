# D365 custom-service contracts

All operations are backend-only HTTP **POST** requests to `D365_BASE_URL` with an Entra client-credentials bearer token. MSAL acquires the resource scope `<D365_BASE_URL>/.default`; the integration client caches/reuses tokens. Never send this token to React.

The supplied existing group is `UBHRApplicationServiceGroup`, with service `UBHRApplicationService`; its live contracts have not been captured. The new [X++ source bundle](../d365/README.md) implements all six adapter operations under **`UBHRPortalServiceGroup/UBHRPortalService`**, preserving those existing objects. Its [manifest](../d365/contracts-manifest.json) and [complete examples](../d365/examples/README.md) specify the exact source-pack DTOs. Examples are fictional contract fixtures, not recorded live responses. F&O compilation, synchronization and deployment remain required.

## Operation status

| Operation | Configuration | External status |
| --- | --- | --- |
| `getOpenRequirements` | `D365_REQUIREMENT_PATH` | Source provided; F&O deployment/live acceptance pending |
| `submitApplication` | `D365_SUBMIT_APPLICATION_PATH` | Source provided; F&O deployment/live acceptance pending |
| `saveCandidateEvaluation` | `D365_SAVE_EVALUATION_PATH` | Source provided; F&O deployment/live acceptance pending |
| `getTopCandidates` | `D365_TOP_CANDIDATES_PATH` | Source provided; F&O deployment/live acceptance pending |
| `getMyApplications` | `D365_MY_APPLICATIONS_PATH` | Source provided; F&O deployment/live acceptance pending |
| `getApplication` | `D365_APPLICATION_PATH` | Source provided; F&O deployment/live acceptance pending |

Configure these paths after deploying the new source pack:

```dotenv
D365_REQUIREMENT_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getOpenRequirements
D365_SUBMIT_APPLICATION_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/submitApplication
D365_SAVE_EVALUATION_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/saveCandidateEvaluation
D365_TOP_CANDIDATES_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getTopCandidates
D365_MY_APPLICATIONS_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getMyApplications
D365_APPLICATION_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getApplication
```

The default `backend/.env.example` retains the reported existing paths and blank pending paths until you deploy a service. After deployment, merge [d365/backend.env.example](../d365/backend.env.example) into ignored `backend/.env`. An empty configured path produces an explicit integration/configuration error. Connected mode never returns a fictional success.

## Request wrappers and mappings

X++ parameter names are part of the method contract. A parameterless operation may accept `{}`; a request-contract parameter may require `{"_request": {...}}`. Do not apply `_request` to every method blindly.

`D365_REQUEST_WRAPPERS` configures the wrapper independently for each internal operation. An empty wrapper means a flat body. `D365_REQUEST_FIELD_MAPS` and `D365_RESPONSE_FIELD_MAPS` centralize differences between actual X++ field names and the canonical backend model. Both map **canonical snake_case key → actual D365 field name**, grouped by internal operation. These settings are JSON objects in the backend environment.

```dotenv
D365_REQUEST_WRAPPERS={"get_open_requirements":"","submit_application":"_request","save_candidate_evaluation":"_request","get_top_candidates":"_request","get_my_applications":"_request","get_application":"_request"}
D365_REQUEST_FIELD_MAPS={"submit_application":{"requirement_id":"JobRequestId"}}
D365_RESPONSE_FIELD_MAPS={"get_open_requirements":{"requirement_id":"JobRequestId","title":"PositionTitle"}}
```

The field names in this mapping example are illustrative. The implementation has standard PascalCase aliases; overrides alter a particular deployed contract. A wrapper override changes nesting only; it does not invent a missing X++ parameter or add an arbitrary request body.

An empty request-field mapping value omits that optional field, for example `{"submit_application":{"consent_accepted":""}}`. Use this only to align a verified existing contract; essential ownership, consent, stable-ID, and idempotency behavior must still exist in the complete integration design.

The optional profile snapshot maps canonical `linkedin_profile` to the proposed `LinkedInProfileJson` memo field. If an existing X++ request contract has not yet been extended, temporarily omit it with `D365_REQUEST_FIELD_MAPS={"submit_application":{"linkedin_profile":""}}` (merge this entry with any existing mappings). Contact submission still works, but the provider profile snapshot is not persisted in D365 until the field and contract are deployed and that omission is removed. A field-name override can target an equivalent existing memo field. The portal does not create X++ fields itself.

Start by obtaining sanitized example requests/responses and exact X++ signatures for each operation. Keep the canonical frontend/API model unchanged while adjusting the adapter's aliases or configuration. Unknown optional fields must not be turned into invented facts; missing required identifiers, invalid JSON collections, and contradictory records are contract errors.

## 1. `getOpenRequirements`

Default invocation is parameterless with an unwrapped empty body:

```json
{}
```

Confirm the method's legal-entity behavior in D365: a parameterless response must be restricted to the intended company by its implementation/service-user context. If the actual operation requires a company/request parameter, adapt the centralized payload builder to that verified contract. Wrapper and field-map settings alone cannot add a field to the empty default payload. Illustrative response:

```json
{
  "Requirements": [
    {
      "RequirementId": "REQ-0001",
      "JobTitle": "Full Stack Developer",
      "JobDescription": "Build accessible React applications and Python services on Azure.",
      "Responsibilities": "Implement interfaces, develop APIs, and maintain deployed services.",
      "RequiredSkills": "React, Python, FastAPI, SQL",
      "PreferredSkills": "Azure, Docker",
      "MinimumExperienceYears": 3,
      "MaximumExperienceYears": 6,
      "RequiredQualifications": "Relevant technical education or equivalent practical experience",
      "RequiredCertifications": "",
      "Department": "Engineering",
      "JobLocation": "Hyderabad",
      "WorkMode": "Hybrid",
      "EmploymentType": "FullTime",
      "NumberOfOpenings": 2,
      "JobStatus": "Open",
      "PublishedDateTime": "2026-10-01T09:00:00Z",
      "ClosingDateTime": "2026-11-01T23:59:59Z",
      "RubricVersion": "v1",
      "EvaluationCriteriaJson": "{}"
    }
  ]
}
```

Return the complete description and job-related fields, not a card-length summary. The backend restricts candidates to open eligible jobs and rechecks submission eligibility. Enforce eligibility in the D365 write transaction too. Map actual numeric enum values explicitly when necessary; do not assume they match these human-readable labels.

## 2. `submitApplication`

Proposed canonical request, with `_request` configurable:

```json
{
  "_request": {
    "Company": "DAT",
    "RequirementId": "REQ-0001",
    "LinkedInIssuer": "https://www.linkedin.com/oauth",
    "LinkedInSub": "verified-oidc-subject",
    "LinkedInProfileJson": "{\"sub\":\"verified-oidc-subject\",\"issuer\":\"https://www.linkedin.com/oauth\",\"name\":\"Alex Example\",\"given_name\":\"Alex\",\"family_name\":\"Example\",\"email\":\"alex@example.com\",\"email_verified\":true}",
    "FullName": "Alex Example",
    "Email": "alex@example.com",
    "Phone": "",
    "LinkedInUrl": "",
    "ResumeFileName": "resume.pdf",
    "ResumeBlobKey": "azure:0123456789abcdef0123456789abcdef.pdf",
    "ResumeSha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "JDHash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "ConsentAccepted": true,
    "ConsentVersion": "v1",
    "ConsentDateTime": "2026-10-13T09:00:00Z",
    "IdempotencyKey": "stable-submission-request-key"
  }
}
```

Identity comes from the validated backend session, never trusted form identity fields. The private storage reference is metadata; no document Base64 is sent. The new source pack persists `IdempotencyKey` uniquely with an immutable submission content digest. `JDHash` and `ResumeSha256` are required 64-character SHA-256 values, supplied by the backend. The example hashes above are fictional.

`FullName`, `Email`, `Phone`, and `LinkedInUrl` are the contact details the candidate confirmed for this application. `LinkedInProfileJson` is separate provider metadata: it contains the validated subject/issuer plus only available allowlisted name, given/family name, valid email, email-verification, HTTPS picture, and locale fields. Its nested keys retain OIDC snake_case names. It is omitted if no LinkedIn profile snapshot exists. The authenticated subject also stays in `LinkedInSub`; never infer a public profile URL or use a member URN as an email. Access/ID/refresh tokens and raw OAuth responses must not be stored in candidate/application tables.

Persist and return the backend-created `ResumeBlobKey` **unchanged**, including its `azure:` prefix. The storage adapter accepts `azure:<32 lowercase hex>.pdf/.docx` and demo `local:<32 lowercase hex>.pdf/.docx` references. A standalone blob path, public URL, or browser-provided reference is not interchangeable with that format.

Expected success shape:

```json
{
  "Success": true,
  "ApplicationId": "APP-000125",
  "Message": "Application submitted successfully"
}
```

Return a stable, non-empty `ApplicationId` belonging to the submitted candidate/requirement. Without it the backend cannot reliably queue or persist evaluations and returns a contract error rather than inventing an identifier. D365 must atomically reuse the same application for a retried idempotency key. Its candidate upsert should match issuer/subject, preserve company boundaries, validate the open requirement, and create the application in one transaction.

Before acknowledging success, that transaction must save the candidate's basic contact information and optional provider-profile snapshot to the candidate master, then create the linked application with its confirmed contact snapshot, consent, and document reference. Only after acknowledgement does the backend queue resume/JD comparison. The AI result is saved through the separate `saveCandidateEvaluation` operation below; sign-in and profile prefill do not trigger either application submission or AI processing.

## 3. `saveCandidateEvaluation`

Suggested path after deployment:

```text
/api/services/UBHRPortalServiceGroup/UBHRPortalService/saveCandidateEvaluation
```

Proposed request:

```json
{
  "_request": {
    "Company": "DAT",
    "ApplicationId": "APP-000125",
    "Score": 88,
    "MeetsMinimumCriteria": true,
    "MatchLabel": "StrongEvidence",
    "ScoreJustification": "Documented project work supports React and FastAPI; Azure evidence is absent.",
    "Summary": "Relevant implementation evidence is present, with cloud experience requiring human verification.",
    "MatchedSkillsJson": "[{\"Requirement\":\"React\",\"ResumeSection\":\"Projects\",\"ProjectName\":\"Employee Portal\",\"Evidence\":\"Developed a frontend application using React.\",\"Reason\":\"Describes direct implementation.\",\"EvidenceStrength\":\"Strong\"}]",
    "PartiallyMatchedJson": "[]",
    "MissingSkillsJson": "[{\"Requirement\":\"Azure\",\"Reason\":\"Not evidenced in the supplied resume.\"}]",
    "EvidenceJson": "[{\"Requirement\":\"React\",\"ResumeSection\":\"Projects\",\"ProjectName\":\"Employee Portal\",\"Evidence\":\"Developed a frontend application using React.\",\"Reason\":\"Describes direct implementation.\",\"EvidenceStrength\":\"Strong\"}]",
    "EvaluationConfidence": "Medium",
    "ModelDeployment": "gpt-4.1-mini",
    "PromptVersion": "v1",
    "RubricVersion": "v1",
    "RequirementId": "REQ-0001",
    "EvaluatedDateTime": "2026-10-13T09:02:00Z",
    "IdempotencyKey": "evaluation:APP-000125"
  }
}
```

`88` is illustrative. The production score comes from Azure OpenAI and is validated, not recomputed by Python. Collection fields are JSON **strings** because X++ memo fields store text; empty collections serialize as `"[]"`. The new source-pack DTO uses actual JSON booleans; its table uses standard `NoYes` for the persisted criteria flag. A different existing service's wire representation must be mapped explicitly.

Expected response:

```json
{"Success": true, "ApplicationId": "APP-000125"}
```

Resolve the application in the configured company and upsert its one current evaluation transactionally. A repeated worker attempt must not create another evaluation. Set `AIStatus=Completed` only after the evaluation is actually saved. The source pack acknowledges a stable `EvaluationId`. Application reads return the completion time at **application-level** `EvaluatedDateTime`; the nested `Evaluation` does not contain that member because the backend's strict evaluation model excludes it. JD/resume hashes are kept on the application.

If the path is missing or D365 rejects the write, the worker must retain/report the processing failure or pending retry rather than claiming D365 persistence. Persisting Processing/Failed state independently requires another supported D365 operation or an extension to this contract.

## 4. `getTopCandidates`

Suggested path after deployment:

```text
/api/services/UBHRPortalServiceGroup/UBHRPortalService/getTopCandidates
```

Proposed request:

```json
{"_request": {"Company": "DAT", "RequirementId": "REQ-0001", "Limit": 25}}
```

The source pack returns typed application rows with a nested `Evaluation`; see the [exact source-pack response](../d365/examples/getTopCandidates.response.json). The adapter also supports older flattened rows such as this illustrative alternative:

```json
{
  "Candidates": [
    {
      "CandidateId": "CAN-001",
      "CandidateName": "Alex Example",
      "Email": "alex@example.com",
      "LinkedInUrl": "",
      "ApplicationId": "APP-000125",
      "RequirementId": "REQ-0001",
      "JobTitle": "Full Stack Developer",
      "AppliedDateTime": "2026-10-13T09:00:00Z",
      "Score": 88,
      "MatchLabel": "StrongEvidence",
      "MeetsMinimumCriteria": true,
      "ScoreJustification": "Documented implementation supports several required technologies.",
      "Summary": "Evidence requires human review and verification.",
      "MatchedSkillsJson": "[]",
      "PartiallyMatchedJson": "[]",
      "MissingSkillsJson": "[]",
      "EvidenceJson": "[]",
      "EvaluationConfidence": "Medium",
      "ModelDeployment": "gpt-4.1-mini",
      "PromptVersion": "v1",
      "RubricVersion": "v1",
      "EvaluatedDateTime": "2026-10-13T09:02:00Z",
      "AIStatus": "Completed",
      "HRStatus": "Submitted",
      "ResumeFileName": "resume.pdf",
      "ResumeBlobKey": "azure:0123456789abcdef0123456789abcdef.pdf"
    }
  ]
}
```

Scope records to the selected requirement/company and order by score descending with a stable tie order. The backend validates identifiers, parses nested JSON, and exposes canonical records to authorized HR users. A pending application may have no evaluation; unavailable evidence must stay unavailable. `JobTitle`, deployment/prompt/rubric provenance, and timestamps are useful additional fields; absent optional metadata remains empty/unavailable rather than receiving invented provenance. The selected job can supply the displayed title.

`Limit` returns at most the requested top N; it is **not pagination or a total population count**. Search/filtering over those returned rows cannot claim to search all applications. Add confirmed server-side pagination, total counts, and search parameters before making such claims.

## 5. `getMyApplications`

The new service includes owned history; configure `D365_MY_APPLICATIONS_PATH` after deployment. Its request is:

```json
{"_request":{"Company":"DAT","LinkedInIssuer":"https://www.linkedin.com","LinkedInSub":"validated-subject"}}
```

The response is `{"Applications":[...]}`, using the application DTO with immutable owner fields and nullable nested `Evaluation`. The backend supplies issuer/subject from the authenticated session and verifies every returned row's ownership. See the [full history example](../d365/examples/getMyApplications.response.json).

## 6. `getApplication`

Configure `D365_APPLICATION_PATH` after deploying this operation. Its request is:

```json
{"_request":{"Company":"DAT","ApplicationId":"returned-stable-application-id"}}
```

The source pack returns a single [application DTO directly](../d365/examples/getApplication.response.json), including immutable issuer/subject, document reference and nullable nested evaluation. Only the trusted backend integration identity receives this service capability. FastAPI checks candidate ownership or an authenticated HR role before returning detail/document responses.

Without the configured read paths, connected candidate history/detail reports an integration error rather than returning fixtures. The notes below describe supported older-service fallback behavior, not the new six-operation deployment.

History requests must scope by company and the validated LinkedIn issuer/subject. Single-application reads must return stable application/requirement IDs, owner issuer/subject, existing status, filename, and the private resume storage reference as required. Backend ownership validation remains mandatory even if D365 filters. HR document retrieval needs a trusted D365 application record/storage reference; arbitrary browser-supplied blob keys are never sufficient authorization.

When `D365_APPLICATION_PATH` is empty, HR candidate detail and resume endpoints retrieve the selected requirement's top 100 candidates through `getTopCandidates` and locate the requested application in those returned records. HR resume requests must include `?requirement_id=REQ-0001` in that mode. An application outside the returned top 100 cannot be resolved by this fallback and returns not found. Configure the single-application read for reliable access beyond that ranked subset; do not describe the fallback as unrestricted application lookup.

## Live acceptance checklist for the D365 team

Capture sanitized contracts and verify: resource token permissions; company scoping; full job fields; open-job checks; candidate upsert identity; submit stable ID and ambiguous-timeout retries; evaluation upsert and timestamps; nested JSON serialization; job-specific descending ranking; detail evidence fields; and authorized private document references. Test non-success bodies, missing IDs, invalid JSON, and cross-company/owner access. These are live integration acceptance checks, not claims of completed external validation.
