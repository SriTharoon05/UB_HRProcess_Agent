# Three-operation D365 contract

The current source pack targets the user's existing model `UBHR_Nive` and tables `UBJobRequirementTable`, `UBCandidateTable`, `UBJobApplicationTable`, `UBHRMatchEvaluationTable`. Follow the [Visual Studio paste guide](../d365/README.md). The default connected adapter is `D365_CONTRACT_MODE=sqlite`: it calls F&O for jobs, application submission and core AI persistence, while portal metadata/history/ranking remain in SQLite.

React calls FastAPI `/api` and `/auth`; **all D365 settings go in `backend/.env`**. Use the deployed F&O origin in `D365_BASE_URL` and configure these relative POST paths:

| Backend setting | F&O path |
| --- | --- |
| `D365_REQUIREMENT_PATH` | `/api/services/UBHRPortalServiceGroup/UBHRPortalService/getOpenRequirements` |
| `D365_SUBMIT_APPLICATION_PATH` | `/api/services/UBHRPortalServiceGroup/UBHRPortalService/submitApplication` |
| `D365_SAVE_EVALUATION_PATH` | `/api/services/UBHRPortalServiceGroup/UBHRPortalService/saveCandidateEvaluation` |

These are source-pack routes, not a claim that they are already deployed. Leave the three old history/ranking/detail paths empty in sqlite mode. `D365_CONTRACT_MODE=legacy` retains the older six-operation adapter for an explicitly configured old deployment; its DTOs are not included in this simplified pack.

## 1. getOpenRequirements

POST body is `{}`. It reads the integration user's current company and returns:

```json
{
  "Requirements": [
    {
      "RequirementId": "REQ-TEST-001",
      "JobTitle": "Full Stack Developer",
      "JobDescription": "Complete job description",
      "Responsibilities": "Build and support recruitment applications",
      "RequiredSkills": "React, Python",
      "PreferredSkills": "Azure",
      "RequiredQualifications": "Relevant degree or equivalent experience",
      "RequiredCertifications": "",
      "Department": "Engineering",
      "JobLocation": "Bengaluru",
      "WorkMode": "Hybrid",
      "EmploymentType": "FullTime",
      "MinimumExperienceYears": 2,
      "MaximumExperienceYears": 6,
      "NumberOfOpenings": 1,
      "RequirementStatus": "Open",
      "OpenDate": "2026-01-01",
      "CloseDate": "2027-12-31",
      "EvaluationCriteriaJson": "{}",
      "RubricVersion": "v1"
    }
  ]
}
```

All names match existing requirement fields. The service reads `RequirementStatus` and inclusive `OpenDate`/`CloseDate` bounds; the separate `JobStatus` and `ClosingDateTime` are unused. `WorkMode`/`EmploymentType` serialize their actual enum element names or stored text. Eligible rows return canonical `RequirementStatus="Open"` even if you configure the local active symbol as `Active`/`Approved`, so the React job filter remains stable. The backend maps the status/dates to its canonical job model and parses comma/newline-delimited skills and JSON criteria. Full JD and the selected evaluation criteria are required for meaningful comparison; do not return only a short job card.

## 2. submitApplication

```json
{
  "_request": {
    "Company": "DAT",
    "ApplicationId": "APP-11111111-1111-4111-8111-111111111111",
    "RequirementId": "REQ-TEST-001",
    "FirstName": "Alex",
    "LastName": "Example",
    "Email": "alex@example.com",
    "Phone": "",
    "LinkedInProfileUrl": "",
    "LinkedInIssuer": "https://www.linkedin.com/oauth",
    "LinkedInSub": "verified-provider-subject"
  }
}
```

The backend creates and durably freezes the application ID and complete submission in SQLite **before** this call. Contact names split into `FirstName` and `LastName`; the original confirmed full name stays in SQLite. Identity comes from the validated server session. Name/email never replace the issuer/subject identity pair, and no member URN is treated as an email or public profile URL.

The F&O transaction validates the active requirement, matches/upserts a candidate using the SHA-256 `IdentityKey`, and inserts the linked application. Existing `initValue()` controls candidate/application human status; the configured pending AI symbol is assigned. Technical fields such as document references, consent and application timestamp are not sent or assigned. Expected acknowledgement:

```json
{
  "Success": true,
  "ApplicationId": "APP-11111111-1111-4111-8111-111111111111",
  "CandidateId": "CAN-22222222-2222-4222-8222-222222222222",
  "EvaluationId": "",
  "Message": "Application submitted successfully"
}
```

Success must be a real JSON boolean, and the returned ApplicationId must equal the frozen ID. CandidateId must be non-empty and stable. A repeated application ID for the same identity/job returns the existing application without another insert, even if the job later closes. SQLite rejects reuse of the submission key with changed contact/resume/job payload; F&O additionally rejects IDs bound to another candidate/job. Unique existing ID/identity indexes are required for concurrent retry safety.

Only after acknowledgement does the backend queue AI work. LinkedIn sign-in and profile prefill alone create neither application nor evaluation.

## 3. saveCandidateEvaluation

```json
{
  "_request": {
    "Company": "DAT",
    "EvaluationId": "EVA-11111111-1111-4111-8111-111111111111",
    "ApplicationId": "APP-11111111-1111-4111-8111-111111111111",
    "RequirementId": "REQ-TEST-001",
    "Score": 73,
    "MeetsMinimumCriteria": true,
    "MatchLabel": "PartialEvidence",
    "Summary": "Relevant implementation is documented; cloud experience requires review.",
    "MatchedSkillsJson": "[]",
    "MissingSkillsJson": "[]",
    "EvidenceJson": "[]"
  }
}
```

The score is illustrative; the real score comes from validated Azure OpenAI output. Array members are **JSON strings**, matching existing text fields. `MeetsMinimumCriteria` is a JSON boolean in the DTO; the service maps it to the existing NoYes/integer field.

The backend derives one stable EvaluationId from the ApplicationId and saves the full validated result in SQLite before delivery. F&O verifies application/job linkage and upserts that evaluation in `UBHRMatchEvaluationTable`, then writes the same score to application `OverallScore` and sets configured completed `AIStatus` in the transaction. It does not change human review status. Expected acknowledgement:

```json
{
  "Success": true,
  "ApplicationId": "APP-11111111-1111-4111-8111-111111111111",
  "CandidateId": "CAN-22222222-2222-4222-8222-222222222222",
  "EvaluationId": "EVA-11111111-1111-4111-8111-111111111111",
  "Message": "Evaluation saved successfully"
}
```

The backend requires matching ApplicationId/EvaluationId before exposing the confirmed result. Retries reuse the ID; a save failure remains pending/failed locally and does not claim F&O completion. Score justification, partial evidence, confidence, model/prompt/rubric versions and evaluated time remain in SQLite, so no extra evaluation columns are required.

## SQLite reads and acceptance

Portal detail, candidate-owned history and job-specific HR ranking read only acknowledged portal submissions from SQLite; backend ownership/role checks still apply. Existing F&O applications are not automatically imported. F&O recruiter status edits are not synchronized: the portal currently retains its initial human-review `Submitted` snapshot. Add a reviewed synchronization capability later if live status updates are needed; this three-operation package does not include one.

The API and worker must use the same durable SQLite file, Redis namespace and private Blob container. `RETENTION_DAYS` does not erase SQLite business metadata automatically. See [schema](d365-schema.md) and [deployment](deployment.md) for persistence and backup limits.

Use the [three-operation Postman collection](../d365/UBHRPortal.postman_collection.json) for serialized F&O checks. Use the portal and a real synthetic upload for the full workflow: direct fixture calls do not populate SQLite or create private documents. X++ compilation, existing enum/EDT compatibility, dedicated-user security, legal-entity scope, duplicate retries and live AI/Blob persistence remain F&O/deployment acceptance checks.
