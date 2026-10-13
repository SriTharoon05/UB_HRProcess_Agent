# D365 custom-service contracts

All operations are backend-only HTTP **POST** requests to `D365_BASE_URL` with an Entra client-credentials bearer token. MSAL acquires the resource scope `<D365_BASE_URL>/.default`; the integration client caches/reuses tokens. Never send this token to React.

The service group supplied in the requirements is `UBHRApplicationServiceGroup`, with service `UBHRApplicationService`. The two existing operations' precise contracts have not been supplied or tested against the live environment. The examples below are **proposed integration contracts**, not recorded D365 responses. No X++ service/table deployment is performed by this repository.

## Operation status

| Operation | Configuration | External status |
| --- | --- | --- |
| `getOpenRequirements` | `D365_REQUIREMENT_PATH` | Reported existing; request/response contract must be confirmed |
| `submitApplication` | `D365_SUBMIT_APPLICATION_PATH` | Reported existing; stable ID and idempotency contract must be confirmed |
| `saveCandidateEvaluation` | `D365_SAVE_EVALUATION_PATH` | Pending X++ implementation/deployment; example value intentionally empty |
| `getTopCandidates` | `D365_TOP_CANDIDATES_PATH` | Pending X++ implementation/deployment; example value intentionally empty |

Suggested existing paths:

```dotenv
D365_REQUIREMENT_PATH=/api/services/UBHRApplicationServiceGroup/UBHRApplicationService/getOpenRequirements
D365_SUBMIT_APPLICATION_PATH=/api/services/UBHRApplicationServiceGroup/UBHRApplicationService/submitApplication
D365_SAVE_EVALUATION_PATH=
D365_TOP_CANDIDATES_PATH=
```

After the D365 team deploys the new methods, set their verified relative paths. An empty configured path produces an explicit integration/configuration error. Connected mode never returns a fictional success.

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

Start by obtaining sanitized example requests/responses and exact X++ signatures for each operation. Keep the canonical frontend/API model unchanged while adjusting the adapter's aliases or configuration. Unknown optional fields must not be turned into invented facts; missing required identifiers, invalid JSON collections, and contradictory records are contract errors.

## 1. `getOpenRequirements` — existing

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

## 2. `submitApplication` — existing

Proposed canonical request, with `_request` configurable:

```json
{
  "_request": {
    "Company": "DAT",
    "RequirementId": "REQ-0001",
    "LinkedInIssuer": "https://www.linkedin.com/oauth",
    "LinkedInSub": "verified-oidc-subject",
    "FullName": "Alex Example",
    "Email": "alex@example.com",
    "Phone": "",
    "LinkedInUrl": "",
    "ResumeFileName": "resume.pdf",
    "ResumeBlobKey": "azure:0123456789abcdef0123456789abcdef.pdf",
    "ResumeSha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "ConsentAccepted": true,
    "ConsentVersion": "v1",
    "ConsentDateTime": "2026-10-13T09:00:00Z",
    "IdempotencyKey": "stable-submission-request-key"
  }
}
```

Identity comes from the validated backend session, never trusted form identity fields. The private storage reference is metadata; no document Base64 is sent. `IdempotencyKey` is a proposed integration requirement that must be supported or mapped to an existing D365 request reference.

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

## 3. `saveCandidateEvaluation` — pending

Suggested path after deployment:

```text
/api/services/UBHRApplicationServiceGroup/UBHRApplicationService/saveCandidateEvaluation
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

`88` is illustrative. The production score comes from Azure OpenAI and is validated, not recomputed by Python. Collection fields are JSON **strings** because X++ memo fields store text; empty collections serialize as `"[]"`. Confirm whether the deployed service expects NoYes integers or JSON booleans and map accordingly.

Expected response:

```json
{"Success": true, "ApplicationId": "APP-000125"}
```

Resolve the application in the configured company and upsert its one current evaluation transactionally. A repeated worker attempt must not create another evaluation. Set `AIStatus=Completed` only after the evaluation is actually saved. The service should assign/return `EvaluatedDateTime`; optional trace metadata may include a stable evaluation ID, JD hash, and resume hash if supported by the confirmed contract.

If the path is missing or D365 rejects the write, the worker must retain/report the processing failure or pending retry rather than claiming D365 persistence. Persisting Processing/Failed state independently requires another supported D365 operation or an extension to this contract.

## 4. `getTopCandidates` — pending

Suggested path after deployment:

```text
/api/services/UBHRApplicationServiceGroup/UBHRApplicationService/getTopCandidates
```

Proposed request:

```json
{"_request": {"Company": "DAT", "RequirementId": "REQ-0001", "Limit": 25}}
```

Proposed response supporting the complete HR detail view:

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
      "HRStatus": "New",
      "ResumeFileName": "resume.pdf",
      "ResumeBlobKey": "azure:0123456789abcdef0123456789abcdef.pdf"
    }
  ]
}
```

Scope records to the selected requirement/company and order by score descending with a stable tie order. The backend validates identifiers, parses nested JSON, and exposes canonical records to authorized HR users. A pending application may have no evaluation; unavailable evidence must stay unavailable. `JobTitle`, deployment/prompt/rubric provenance, and timestamps are useful additional fields; absent optional metadata remains empty/unavailable rather than receiving invented provenance. The selected job can supply the displayed title.

`Limit` returns at most the requested top N; it is **not pagination or a total population count**. Search/filtering over those returned rows cannot claim to search all applications. Add confirmed server-side pagination, total counts, and search parameters before making such claims.

## Additional read capabilities

The four operations above do not define a candidate-owned application-history service or a general application lookup. Optional `D365_MY_APPLICATIONS_PATH` and `D365_APPLICATION_PATH` allow a separately deployed read contract. Without them, connected candidate history/detail operations report the unsupported integration capability instead of showing fixtures or another candidate's records.

History requests must scope by company and the validated LinkedIn issuer/subject. Single-application reads must return stable application/requirement IDs, owner issuer/subject, existing status, filename, and the private resume storage reference as required. Backend ownership validation remains mandatory even if D365 filters. HR document retrieval needs a trusted D365 application record/storage reference; arbitrary browser-supplied blob keys are never sufficient authorization.

When `D365_APPLICATION_PATH` is empty, HR candidate detail and resume endpoints retrieve the selected requirement's top 100 candidates through `getTopCandidates` and locate the requested application in those returned records. HR resume requests must include `?requirement_id=REQ-0001` in that mode. An application outside the returned top 100 cannot be resolved by this fallback and returns not found. Configure the single-application read for reliable access beyond that ranked subset; do not describe the fallback as unrestricted application lookup.

## Live acceptance checklist for the D365 team

Capture sanitized contracts and verify: resource token permissions; company scoping; full job fields; open-job checks; candidate upsert identity; submit stable ID and ambiguous-timeout retries; evaluation upsert and timestamps; nested JSON serialization; job-specific descending ranking; detail evidence fields; and authorized private document references. Test non-success bodies, missing IDs, invalid JSON, and cross-company/owner access. These are live integration acceptance checks, not claims of completed external validation.
