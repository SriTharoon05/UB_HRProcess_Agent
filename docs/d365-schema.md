# Proposed D365 business schema

D365 Finance & Operations is the business system of record. The portal communicates through JSON custom services; it does not connect to D365 SQL and does not maintain a second SQL business database. Redis holds temporary sessions, submission coordination, job state, and cached processing context. Azure Blob Storage holds private documents.

These are proposed logical tables and field definitions for the D365 team to review in Visual Studio 2022/X++. The existing requirement table's physical name, extended data types, enum values, and service fields have not been verified. Reuse existing candidate/application tables when suitable. The Python adapter normalizes service contracts; it does not create tables or deploy X++.

## Relationships

```mermaid
erDiagram
    ExistingJobRequirement ||--o{ UBHRJobApplication : receives
    UBHRCandidate ||--o{ UBHRJobApplication : submits
    UBHRJobApplication ||--o| UBHRMatchEvaluation : has_current_evaluation
    ExistingJobRequirement ||--o{ UBHRMatchEvaluation : provides_context
```

`RecId` is the D365 technical identifier. `RequirementId`, `CandidateId`, `ApplicationId`, and `EvaluationId` are stable external identifiers. An application links one candidate, one requirement, the uploaded document reference, and at most one current evaluation. One candidate may apply for several requirements.

## Existing job requirement table

Suggested logical name: `UBHRJobRequirement`. **Do not assume this is the actual physical table name.**

| Field | Proposed D365 type | Meaning |
| --- | --- | --- |
| RecId | Int64 | System record identifier |
| RequirementId | String(40) | Stable job identifier |
| JobTitle | String(200) | Advertised title |
| JobDescription | Memo | Complete description used for evaluation |
| Responsibilities | Memo | Job responsibilities |
| RequiredSkills | Memo | Required job skills |
| PreferredSkills | Memo | Preferred job skills |
| MinimumExperienceYears | Real | Minimum relevant experience, when provided |
| MaximumExperienceYears | Real | Advertised upper range, when provided |
| RequiredQualifications | Memo | Job-related qualifications |
| RequiredCertifications | Memo | Job-related certifications |
| Department | String(100) | Department |
| JobLocation | String(150) | Advertised location |
| WorkMode | Enum | Remote / Hybrid / Onsite |
| EmploymentType | Enum | FullTime / PartTime / Contract / Internship |
| NumberOfOpenings | Integer | Available positions |
| JobStatus | Enum | Draft / Open / Closed |
| PublishedDateTime | UtcDateTime | Publication time |
| ClosingDateTime | UtcDateTime | Application deadline |
| HiringManagerWorkerRecId | Int64 | Optional hiring manager worker reference |
| RubricVersion | String(20) | Optional criteria version |
| EvaluationCriteriaJson | Memo | Optional structured criteria; no numerical weights required |
| DataAreaId | String | Legal entity/company |
| CreatedDateTime | UtcDateTime | Creation time |
| ModifiedDateTime | UtcDateTime | Latest modification time |

Return open, currently eligible requirements. Recheck eligibility at application submission and inside the D365 transaction to prevent a closure race. Return the complete JD and relevant responsibilities, skills, qualifications, certifications, and optional criteria. Omitted optional fields remain unavailable; they must not be populated with invented job facts.

## Candidate master: `UBHRCandidate`

| Field | Proposed D365 type | Meaning |
| --- | --- | --- |
| RecId | Int64 | System record identifier |
| CandidateId | String(40) | Stable candidate identifier |
| LinkedInIssuer | String(100) | Validated OIDC issuer |
| LinkedInSub | String(255) | Validated OIDC subject |
| FullName | String(200) | Candidate name |
| Email | String(320) | Candidate contact email |
| Phone | String(30) | Optional contact number |
| LinkedInUrl | String(500) | Optional candidate-supplied URL |
| ConsentDateTime | UtcDateTime | Consent capture timestamp |
| CreatedDateTime | UtcDateTime | Creation time |
| ModifiedDateTime | UtcDateTime | Latest modification time |
| DataAreaId | String | Legal entity/company |

Identity is `(LinkedInIssuer, LinkedInSub)` within the chosen company policy, never name or email. LinkedIn's `openid profile email` scopes do not guarantee complete contact information, a profile URL, employment history, or skills. The application form prefills available profile data and collects the required full name and contact email plus optional contact fields. These editable fields do not replace the authenticated identity. Upsert an existing identity before creating a new candidate.

## Job application: `UBHRJobApplication`

| Field | Proposed D365 type | Meaning |
| --- | --- | --- |
| RecId | Int64 | System record identifier |
| ApplicationId | String(40) | Stable application identifier returned by submit service |
| CandidateRecId | Int64 | Foreign key to candidate `RecId` |
| RequirementRecId | Int64 | Foreign key to actual requirement table `RecId` |
| RequirementId | String(50) | External job identifier |
| ResumeFileName | String(255) | Sanitized display filename |
| ResumeBlobKey | String(500) | Private storage object reference, not a public URL |
| ResumeSha256 | String(64) | SHA-256 of uploaded document |
| ResumeExtractJson | Memo | Optional extracted resume data subject to retention policy |
| JDHash | String(64) | SHA-256 of the complete JD context used for evaluation |
| AppliedDateTime | UtcDateTime | Submission time |
| AIStatus | Enum | Pending / Processing / Completed / Failed |
| HRStatus | Enum | New / Reviewing / Interview / Closed |
| ConsentVersion | String(20) | Accepted privacy/processing notice version |
| CreatedDateTime | UtcDateTime | Creation time |
| ModifiedDateTime | UtcDateTime | Latest modification time |
| DataAreaId | String | Legal entity/company |

Foreign keys: `CandidateRecId → UBHRCandidate.RecId`; `RequirementRecId → ExistingJobRequirementTable.RecId`. Validate that referenced records belong to the authorized company. Resolve the proposed 40/50-character requirement identifier discrepancy to one shared EDT before deployment.

The portal sends a stable idempotency key for retries. The D365 service must persist an equivalent unique request reference atomically, for example an additional `SubmissionIdempotencyKey` EDT/field or the existing integration request table. A Redis lock alone cannot guarantee uniqueness after Redis loss or an ambiguous HTTP timeout. Define separately whether a candidate may submit a revised resume for the same job; the portal's transport idempotency does not decide that business policy.

Never place Base64 documents in ordinary text fields. Store only the private key, checksum, filename, and necessary metadata. Document extraction and cached evaluation context contain personal data and need the same retention controls as documents.

## Current evaluation: `UBHRMatchEvaluation`

| Field | Proposed D365 type | Meaning |
| --- | --- | --- |
| RecId | Int64 | System record identifier |
| EvaluationId | String(40) | Stable evaluation identifier |
| ApplicationRecId | Int64 | Foreign key to application `RecId` |
| RequirementRecId | Int64 | Foreign key to requirement `RecId` |
| Score | Integer | Model-generated evidence alignment, 0–100 |
| MeetsMinimumCriteria | NoYes enum | Model assessment of supporting evidence for minimum criteria |
| MatchLabel | String(30) | StrongEvidence / PartialEvidence / InsufficientEvidence |
| ScoreJustification | Memo | Detailed explanation of model score |
| Summary | Memo | Overall evidence summary |
| MatchedSkillsJson | Memo | Serialized evidenced-requirement objects |
| PartiallyMatchedJson | Memo | Serialized partially evidenced-requirement objects |
| MissingSkillsJson | Memo | Serialized not-evidenced requirement objects |
| EvidenceJson | Memo | Serialized supporting resume evidence |
| EvaluationConfidence | String(20) | High / Medium / Low |
| ModelDeployment | String(100) | Azure OpenAI deployment name |
| PromptVersion | String(30) | Version-controlled prompt identifier |
| RubricVersion | String(30) | Criteria version, if supplied |
| EvaluatedDateTime | UtcDateTime | Evaluation completion time |
| CreatedDateTime | UtcDateTime | Record creation time |
| ModifiedDateTime | UtcDateTime | Latest modification time |
| DataAreaId | String | Legal entity/company |

Foreign keys: `ApplicationRecId → UBHRJobApplication.RecId`; `RequirementRecId → ExistingJobRequirementTable.RecId`. The application determines the requirement; reject a conflicting requirement rather than accepting arbitrary cross-job writes. Upsert one current evaluation per application inside a transaction. Return a clear failure if the application is missing.

The adapter preserves the model's validated score. Labels and minimum-criteria assessments are evidence descriptions, not automatic hiring or rejection decisions. Empty JSON collections are `"[]"`; malformed JSON must raise a contract error. Historical evaluations, if later introduced, need a version/history table and an explicit current-record selection rule.

## Keys and indexes for D365 review

| Table | Required logical uniqueness / recommended lookup indexes |
| --- | --- |
| Requirement | Unique `(DataAreaId, RequirementId)`; lookup `(DataAreaId, JobStatus, ClosingDateTime)` |
| Candidate | Unique `(DataAreaId, CandidateId)` and `(DataAreaId, LinkedInIssuer, LinkedInSub)` |
| Application | Unique `(DataAreaId, ApplicationId)`; unique persisted submission request key; lookups `(DataAreaId, CandidateRecId, AppliedDateTime)` and `(DataAreaId, RequirementRecId, AppliedDateTime)` |
| Evaluation | Unique `(DataAreaId, EvaluationId)` and `(DataAreaId, ApplicationRecId)`; lookup `(DataAreaId, RequirementRecId, Score)` |

Use D365 metadata/EDT/index conventions and assess string index limits; a normalized identity digest can support uniqueness when the issuer/subject composite cannot be indexed directly. System-generated `RecId` remains the technical key. All service reads and writes must apply `Company`/`DataAreaId`, enforce service permissions, and scope joins to the same legal entity. This deployment uses one configured `D365_COMPANY`; a future multi-company UI requires additional authorization and explicit routing.

## Status ownership

`AIStatus` tracks processing; `HRStatus` tracks human review. The current four proposed services do not establish an independent HR status-write operation. The UI therefore displays existing HR status without pretending to save changes. `saveCandidateEvaluation` should set `AIStatus=Completed` in the same transaction as a successful evaluation upsert. Persisting Processing/Failed status or deletion in D365 requires a confirmed write contract; temporary worker status must not be represented as a verified D365 update.
