# D365 F&O table and EDT designer specification

Create these objects in the new `UBHRRecruitmentPortal` model using the Finance and Operations tools in Visual Studio 2022 on an F&O development environment. The ordinary Visual Studio Community/Professional IDE alone does not include the F&O metadata designer or compiler. This specification accompanies the setup guide and X++ sources in this folder; it is not a database SQL script or an importable model package.

The baseline creates four new tables. The existing physical requirement table has not been inspected. If your environment already has an authoritative requirement table, adapt `UBHRPortalService` reads and relations to that verified table instead of creating a second source of job data. Nothing here replaces or modifies the reported existing `UBHRApplicationServiceGroup`.

## Create EDTs first

In your F&O project, right-click the project → **Add → New Item → Data Types → Extended Data Type**, select the base type in the table below, and give the item its exact name. For a String EDT set **StringSize** to the listed character limit. For the Real and Integer EDTs retain the normal numeric base type; optionally set the experience EDT display decimals to 2. Use a label file for production labels; literal English labels can be used while reviewing the sample.

| EDT | Base type | StringSize | Meaning |
| --- | --- | ---: | --- |
| `UBHRExternalId` | String | 40 | Requirement, candidate, application, or evaluation external ID |
| `UBHRIdentityIssuer` | String | 255 | Validated OIDC issuer; never a browser-supplied identity |
| `UBHRIdentitySubject` | String | 255 | Validated OIDC subject; never an email or public profile URL |
| `UBHRHash` | String | 64 | Lowercase hexadecimal SHA-256; also used for IdentityKey |
| `UBHRIdempotencyKey` | String | 128 | Persistent integration request reference |
| `UBHRFullName` | String | 200 | Candidate-confirmed full name |
| `UBHREmail` | String | 320 | Candidate-confirmed contact email |
| `UBHRPhone` | String | 30 | Optional candidate contact phone |
| `UBHRUrl` | String | 500 | Optional candidate-supplied HTTPS LinkedIn profile URL |
| `UBHRResumeFileName` | String | 150 | Sanitized display filename; matches the backend limit |
| `UBHRBlobReference` | String | 500 | Private storage reference including the unchanged azure: prefix |
| `UBHRJobTitle` | String | 200 | Advertised job title |
| `UBHRDepartment` | String | 100 | Advertised department |
| `UBHRJobLocation` | String | 150 | Advertised job location |
| `UBHRCode` | String | 30 | Work mode, employment type, or evidence match label |
| `UBHRVersion` | String | 30 | Prompt or rubric version |
| `UBHRConsentVersion` | String | 20 | Accepted privacy and processing notice version |
| `UBHRModelDeployment` | String | 100 | Actual Azure OpenAI deployment provenance |
| `UBHRConfidence` | String | 20 | Model evidence confidence label |
| `UBHRExperienceYears` | Real | — | Actual minimum or maximum relevant experience in years |
| `UBHRCount` | Integer | — | Actual number of advertised openings |
| `UBHRMatchScore` | Integer | — | Evidence alignment score, validated between 0 and 100 |

Use the existing standard **`Notes`** EDT for every long-text/JSON field, and **`RefRecId`** for foreign-key fields. A Notes field is created as a **String** table field with `ExtendedDataType=Notes`; it inherits the standard long-text behavior. Do not create a field type named Memo, cap full text at an arbitrary 1,000/4,000 characters, or put document Base64 into it. If your model references do not expose `Notes` or `RefRecId`, add the package reference that owns the standard EDT in your F&O installation.

## Create the three base enums

Right-click project → **Add → New Item → Data Types → Base Enum**. Set `IsExtensible=No` for this sample, add elements in the stated order, and keep these explicit values. `WorkMode` and `EmploymentType` are string fields; no extra enum objects are required. Standard `NoYes` already exists.

| Enum | Elements and values |
| --- | --- |
| `UBHRJobStatus` | `Draft=0`, `Open=1`, `Closed=2` |
| `UBHRAIStatus` | `Pending=0`, `Processing=1`, `Completed=2`, `Failed=3` |
| `UBHRHRStatus` | `Submitted=0`, `Reviewing=1`, `Interview=2`, `Rejected=3`, `Hired=4`, `Closed=5` |

The service must emit `Open`, `Pending`, `Completed`, `Submitted`, and the other status names explicitly. Translated labels and raw enum ordinals are not the HTTP response contract. `AIStatus` and `HRStatus` serve separate purposes; this service does not provide an HR-status update method.

## Common table properties

For each table use **Add → New Item → Data Model → Table**. Open the designer and set the following properties before adding fields:

| Property | Value |
| --- | --- |
| `TableType` | `Regular` |
| `SaveDataPerCompany` | `Yes` |
| `CacheLookup` | `None` |
| `CreatedBy` | `Yes` |
| `CreatedDateTime` | `Yes` |
| `ModifiedBy` | `Yes` |
| `ModifiedDateTime` | `Yes` |
| `PrimaryIndex` | `SurrogateKey` |
| `ClusterIndex` | `SurrogateKey` |

`RecId`, `DataAreaId`, and `RecVersion` are F&O system fields. Creation/modification timestamps and user IDs are enabled by the table properties above. **Do not add duplicate custom fields with these names.** Use the system/surrogate `RecId` key for `PrimaryIndex` and `ClusterIndex`; select `SurrogateKey` supplied by the table designer. The replacement key below is the stable external ID index, not the technical primary key.

All four tables are per-company. F&O includes company scope in physical indexes for these tables; the fields shown below are the fields you add in the designer. The service scopes transactions and joins to the configured legal entity and checks referenced records in that company.

Add fields by right-clicking **Fields → New → String / Real / Integer / Int64 / Enum / UtcDateTime**, naming the field exactly, then setting `ExtendedDataType` or `EnumType` as listed. An EDT determines its string size. Set `Mandatory=Yes` for the fields marked Yes; service validation remains required for timestamps, numeric ranges, relationships, JSON and business conditions.

## `UBHRJobRequirement`

Complete published requirement and JD context; adapt the service mapping if an existing requirement table is authoritative.

Additional properties: `TableGroup=Main`, `ReplacementKey=RequirementIdIdx`.

| Field | AOT type / EDT or enum | Mandatory | Meaning |
| --- | --- | --- | --- |
| `RequirementId` | String / `UBHRExternalId` | Yes | Stable external requirement ID, shared consistently with application.RequirementId |
| `JobTitle` | String / `UBHRJobTitle` | No | Advertised job title |
| `JobDescription` | String / `Notes` | No | Complete JD, with no truncation to a card-length summary |
| `Responsibilities` | String / `Notes` | No | Complete responsibilities |
| `RequiredSkills` | String / `Notes` | No | Comma/newline-delimited required skills; the adapter normalizes them to a list |
| `PreferredSkills` | String / `Notes` | No | Comma/newline-delimited preferred skills |
| `MinimumExperienceYears` | Real / `UBHRExperienceYears` | No | Actual advertised minimum; zero means an actual zero-year threshold in this baseline |
| `MaximumExperienceYears` | Real / `UBHRExperienceYears` | No | Actual advertised maximum; publish accurate values |
| `RequiredQualifications` | String / `Notes` | No | Complete required qualifications |
| `RequiredCertifications` | String / `Notes` | No | Comma/newline-delimited required certifications |
| `Department` | String / `UBHRDepartment` | No | Advertised department |
| `JobLocation` | String / `UBHRJobLocation` | No | Advertised location |
| `WorkMode` | String / `UBHRCode` | No | Remote, Hybrid, or Onsite, as an actual string value |
| `EmploymentType` | String / `UBHRCode` | No | FullTime, PartTime, Contract, or Internship |
| `NumberOfOpenings` | Integer / `UBHRCount` | No | Actual number of openings; publication requires a positive value |
| `JobStatus` | Enum / `UBHRJobStatus` | No | Draft / Open / Closed; default Draft |
| `PublishedDateTime` | UtcDateTime | No | Actual UTC publication time |
| `ClosingDateTime` | UtcDateTime | No | Actual UTC closing time; an empty value represents no configured deadline |
| `HiringManagerWorkerRecId` | Int64 / `RefRecId` | No | Optional worker RecId; requires HcmWorker relation if used |
| `RubricVersion` | String / `UBHRVersion` | No | Actual criteria version; empty when not provided |
| `EvaluationCriteriaJson` | String / `Notes` | No | Optional valid JSON object of job-specific evaluation criteria; response emits `{}` when absent |

Indexes: right-click **Indexes → New Index**, set the exact index name and `AllowDuplicates`/`AlternateKey`, then drag/add the listed fields in order.

| Index | Fields in order | AllowDuplicates | AlternateKey |
| --- | --- | --- | --- |
| `RequirementIdIdx` | `RequirementId` | No | Yes |
| `OpenRequirementsIdx` | `JobStatus`, `ClosingDateTime` | Yes | No |

No mandatory table relations.

Optional: if using hiring-manager references, add relation `HiringManagerWorker` → `HcmWorker`, with normal mapping `HiringManagerWorkerRecId → RecId` and `RelatedTableCardinality=ZeroOne`. Add a reference to the HCM model/package that owns `HcmWorker`. Leave the field zero when no manager is selected. This field is not used by the portal service.

After creating all tables and relations, add these **Delete Actions** on this parent table. Set `DeleteAction=Restricted` to retain audit links; deletion and retention need a separately reviewed workflow.

| Delete action name | Child table | Child relation |
| --- | --- | --- |
| `Applications` | `UBHRJobApplication` | `Requirement` |
| `Evaluations` | `UBHRMatchEvaluation` | `Requirement` |

## `UBHRCandidate`

One current contact/profile master per authenticated LinkedIn identity in the configured company.

Additional properties: `TableGroup=Main`, `ReplacementKey=CandidateIdIdx`.

| Field | AOT type / EDT or enum | Mandatory | Meaning |
| --- | --- | --- | --- |
| `CandidateId` | String / `UBHRExternalId` | Yes | Stable CAN- plus 36-character GUID; exactly 40 characters |
| `IdentityKey` | String / `UBHRHash` | Yes | SHA-256 of the service helper's unambiguous issuer/subject encoding; unique per company |
| `LinkedInIssuer` | String / `UBHRIdentityIssuer` | Yes | Validated immutable OIDC issuer |
| `LinkedInSub` | String / `UBHRIdentitySubject` | Yes | Validated immutable OIDC subject |
| `FullName` | String / `UBHRFullName` | Yes | Current candidate-confirmed contact name |
| `Email` | String / `UBHREmail` | Yes | Current candidate-confirmed contact email |
| `Phone` | String / `UBHRPhone` | No | Optional current phone |
| `LinkedInUrl` | String / `UBHRUrl` | No | Optional supplied public profile URL; never derive it from a member URN |
| `LinkedInProfileJson` | String / `Notes` | No | Allowlisted provider profile, separate from edited contact data; no OAuth credentials; service initializes absent JSON to `{}` |
| `ConsentVersion` | String / `UBHRConsentVersion` | Yes | Latest accepted notice version |
| `ConsentDateTime` | UtcDateTime | No | Latest accepted consent timestamp |

Indexes: right-click **Indexes → New Index**, set the exact index name and `AllowDuplicates`/`AlternateKey`, then drag/add the listed fields in order.

| Index | Fields in order | AllowDuplicates | AlternateKey |
| --- | --- | --- | --- |
| `CandidateIdIdx` | `CandidateId` | No | Yes |
| `IdentityKeyIdx` | `IdentityKey` | No | No |

No mandatory table relations.

After creating all tables and relations, add these **Delete Actions** on this parent table. Set `DeleteAction=Restricted` to retain audit links; deletion and retention need a separately reviewed workflow.

| Delete action name | Child table | Child relation |
| --- | --- | --- |
| `Applications` | `UBHRJobApplication` | `Candidate` |

## `UBHRJobApplication`

Immutable per-submission owner, contact, profile, document and consent snapshot, linked to candidate and requirement.

Additional properties: `TableGroup=Transaction`, `ReplacementKey=ApplicationIdIdx`.

| Field | AOT type / EDT or enum | Mandatory | Meaning |
| --- | --- | --- | --- |
| `ApplicationId` | String / `UBHRExternalId` | Yes | Stable APP- plus 36-character GUID; exactly 40 characters |
| `CandidateRecId` | Int64 / `RefRecId` | Yes | FK to UBHRCandidate.RecId in the same company |
| `RequirementRecId` | Int64 / `RefRecId` | Yes | FK to UBHRJobRequirement.RecId in the same company |
| `RequirementId` | String / `UBHRExternalId` | Yes | External requirement ID snapshot, consistent with the related requirement |
| `LinkedInIssuer` | String / `UBHRIdentityIssuer` | Yes | Immutable validated owner issuer snapshot |
| `LinkedInSub` | String / `UBHRIdentitySubject` | Yes | Immutable validated owner subject snapshot |
| `LinkedInProfileJson` | String / `Notes` | No | Provider profile captured for this application; service initializes absent JSON to `{}` |
| `FullName` | String / `UBHRFullName` | Yes | Name confirmed for this application |
| `Email` | String / `UBHREmail` | Yes | Contact email confirmed for this application |
| `Phone` | String / `UBHRPhone` | No | Optional contact phone snapshot |
| `LinkedInUrl` | String / `UBHRUrl` | No | Optional confirmed public profile URL |
| `ResumeFileName` | String / `UBHRResumeFileName` | Yes | Validated PDF/DOCX display filename, maximum 150 characters |
| `ResumeBlobKey` | String / `UBHRBlobReference` | Yes | Backend-owned private reference, unchanged; never a public URL or Base64 document |
| `ResumeSha256` | String / `UBHRHash` | Yes | SHA-256 of the uploaded document bytes |
| `JDHash` | String / `UBHRHash` | Yes | SHA-256 of the complete JD context supplied with the accepted submission |
| `ResumeExtractJson` | String / `Notes` | No | Reserved optional extraction metadata; current service does not populate it |
| `AppliedDateTime` | UtcDateTime | No | Server-assigned UTC application submission time |
| `AIStatus` | Enum / `UBHRAIStatus` | No | Pending initially; Completed only when evaluation transaction commits |
| `HRStatus` | Enum / `UBHRHRStatus` | No | Submitted initially; separate human-review workflow |
| `ConsentVersion` | String / `UBHRConsentVersion` | Yes | Accepted notice version captured for this application |
| `ConsentDateTime` | UtcDateTime | No | Accepted consent timestamp captured for this application |
| `IdempotencyKey` | String / `UBHRIdempotencyKey` | Yes | Unique persistent submit request reference |
| `PayloadHash` | String / `UBHRHash` | Yes | Request-content SHA-256; a retry with changed contents must be rejected |

Indexes: right-click **Indexes → New Index**, set the exact index name and `AllowDuplicates`/`AlternateKey`, then drag/add the listed fields in order.

| Index | Fields in order | AllowDuplicates | AlternateKey |
| --- | --- | --- | --- |
| `ApplicationIdIdx` | `ApplicationId` | No | Yes |
| `IdempotencyKeyIdx` | `IdempotencyKey` | No | No |
| `CandidateDateIdx` | `CandidateRecId`, `AppliedDateTime` | Yes | No |
| `RequirementDateIdx` | `RequirementRecId`, `AppliedDateTime` | Yes | No |

Relations: right-click **Relations → New Relation**, set `RelatedTable`, then add **New → Normal** field mapping under it. Use `RelationshipType=Association`, `Cardinality=ZeroMore`, `RelatedTableCardinality=ExactlyOne` for these mandatory parent references.

| Relation | RelatedTable | Normal field mapping |
| --- | --- | --- |
| `Candidate` | `UBHRCandidate` | `CandidateRecId → RecId` |
| `Requirement` | `UBHRJobRequirement` | `RequirementRecId → RecId` |

After creating all tables and relations, add these **Delete Actions** on this parent table. Set `DeleteAction=Restricted` to retain audit links; deletion and retention need a separately reviewed workflow.

| Delete action name | Child table | Child relation |
| --- | --- | --- |
| `Evaluation` | `UBHRMatchEvaluation` | `Application` |

## `UBHRMatchEvaluation`

One current resume-versus-JD evaluation per application, separate from candidate and application contact information.

Additional properties: `TableGroup=Transaction`, `ReplacementKey=EvaluationIdIdx`.

| Field | AOT type / EDT or enum | Mandatory | Meaning |
| --- | --- | --- | --- |
| `EvaluationId` | String / `UBHRExternalId` | Yes | Stable EVA- plus 36-character GUID; exactly 40 characters |
| `ApplicationRecId` | Int64 / `RefRecId` | Yes | FK to UBHRJobApplication.RecId; unique current evaluation |
| `RequirementRecId` | Int64 / `RefRecId` | Yes | FK to the application's own requirement in the same company |
| `Score` | Integer / `UBHRMatchScore` | No | Actual validated model score, 0–100; no automatic hire or rejection decision |
| `MeetsMinimumCriteria` | Enum / `NoYes` | No | Evidence-based model assessment; DTO serializes this as a JSON boolean |
| `MatchLabel` | String / `UBHRCode` | No | Model evidence label, for example StrongEvidence, PartialEvidence, InsufficientEvidence |
| `ScoreJustification` | String / `Notes` | No | Detailed explanation of the supplied score |
| `Summary` | String / `Notes` | No | Overall evidence summary |
| `MatchedSkillsJson` | String / `Notes` | No | Serialized matched evidence array; service initializes absent JSON to `[]` |
| `PartiallyMatchedJson` | String / `Notes` | No | Serialized partial evidence array; service initializes absent JSON to `[]` |
| `MissingSkillsJson` | String / `Notes` | No | Serialized not-evidenced requirement array; service initializes absent JSON to `[]` |
| `EvidenceJson` | String / `Notes` | No | Serialized relevant evidence array; service initializes absent JSON to `[]` |
| `EvaluationConfidence` | String / `UBHRConfidence` | No | Actual High / Medium / Low confidence label |
| `ModelDeployment` | String / `UBHRModelDeployment` | No | Actual deployment used for this evaluation |
| `PromptVersion` | String / `UBHRVersion` | No | Actual version-controlled scoring prompt |
| `RubricVersion` | String / `UBHRVersion` | No | Actual job rubric version when available |
| `EvaluatedDateTime` | UtcDateTime | No | UTC completion time of the saved evaluation |
| `IdempotencyKey` | String / `UBHRIdempotencyKey` | Yes | Evaluation worker request reference |
| `PayloadHash` | String / `UBHRHash` | Yes | Current evaluation content digest; identical retries reuse it and changed content replaces the current evaluation |

Indexes: right-click **Indexes → New Index**, set the exact index name and `AllowDuplicates`/`AlternateKey`, then drag/add the listed fields in order.

| Index | Fields in order | AllowDuplicates | AlternateKey |
| --- | --- | --- | --- |
| `EvaluationIdIdx` | `EvaluationId` | No | Yes |
| `ApplicationIdx` | `ApplicationRecId` | No | No |
| `RequirementScoreIdx` | `RequirementRecId`, `Score` | Yes | No |

Relations: right-click **Relations → New Relation**, set `RelatedTable`, then add **New → Normal** field mapping under it. Use `RelationshipType=Association` and `RelatedTableCardinality=ExactlyOne`. Set the child cardinality individually: an application has zero or one current evaluation; a requirement can have many evaluations.

| Relation | RelatedTable | Normal field mapping | Cardinality |
| --- | --- | --- | --- |
| `Application` | `UBHRJobApplication` | `ApplicationRecId → RecId` | `ZeroOne` |
| `Requirement` | `UBHRJobRequirement` | `RequirementRecId → RecId` | `ZeroMore` |

## Important storage and retry rules

- **Identity uniqueness:** `IdentityKeyIdx` indexes the 64-character SHA-256 digest produced by the service helper. It uses an unambiguous issuer/subject encoding and UTF-8. The service compares the complete stored issuer and subject after lookup, so a digest mismatch or collision is rejected. Do not use email as identity, and do not create a wide `(LinkedInIssuer, LinkedInSub)` string index that can exceed SQL key limits.
- **External IDs:** `RequirementId`, `CandidateId`, `ApplicationId`, and `EvaluationId` all use the same 40-character EDT. `CAN-`, `APP-`, and `EVA-` plus a 36-character GUID fit exactly. Choose requirement IDs of at most 40 characters; no silent truncation is allowed.
- **Snapshots:** Updating the candidate master for a later application must not change a previous application's contact fields, profile, consent, or owner issuer/subject. The application stores each snapshot independently.
- **Submit idempotency:** `IdempotencyKeyIdx` is a unique persisted key in D365. `PayloadHash` identifies its original request contents. Return the same application on a same-payload retry and reject reuse with changed identity/job/document/contact information. A Redis lock alone is insufficient.
- **One current evaluation:** `ApplicationIdx` is unique on `ApplicationRecId`; evaluation retries update the same logical evaluation transactionally. The stored requirement must match the application requirement. Set application `AIStatus=Completed` only after the evaluation is saved.
- **JSON:** JSON arrays are stored as text such as `[]`, not a comma-joined substitute. Supplied object fields contain valid object text. An absent optional provider snapshot is stored blank; the response DTO emits `{}` for that absence. An absent requirement criteria object also emits `{}`. These are service/DTO defaults, not AOT/SQL default properties. Profile JSON allows only returned public OIDC fields and contains no OAuth credentials.
- **Documents:** `ResumeBlobKey` preserves the exact private reference, including `azure:`. The actual PDF/DOCX remains in private Blob Storage. `ResumeExtractJson` is reserved and unused by the current service; only populate it with an approved extraction and retention policy.
- **Publication:** Job numeric fields hold actual values in this baseline. Enter correct experience thresholds and a positive opening count before publishing; do not treat an unentered zero as unknown job information. A separate presence-flag contract is needed if your real requirement model must distinguish missing numeric values from zero.
- **Company scope:** These indexes are unique within the legal entity. All reads/writes use the configured company and service-user authorization. No direct SQL access from React or FastAPI is required.

## Finish the metadata before pasting service code

Save the EDTs and enums, then all four tables, indexes, and relations. Build the `UBHRRecruitmentPortal` project/model and synchronize its database on the F&O development environment. Resolve metadata errors before compiling the service classes. The JSON companion [table-specification.json](table-specification.json) gives the same names and designer properties for review; it cannot be imported as an AOT package.

This repository has no F&O compiler or database synchronizer. Building and synchronizing in Visual Studio is mandatory; static repository checks do not establish that the objects compile or that any D365 environment was changed.
