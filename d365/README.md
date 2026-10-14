# D365 Finance & Operations implementation guide

This folder contains the X++ source and AOT definitions required to connect this recruitment portal to D365 Finance & Operations. Create the metadata in an F&O development environment, paste the classes, build and synchronize the model, register the integration identity, then configure the **FastAPI backend**. React continues to call FastAPI.

The package uses a new service, `UBHRPortalService`, in `UBHRPortalServiceGroup`. It does not overwrite the reported existing `UBHRApplicationService` or `UBHRApplicationServiceGroup`. The physical definition of your existing requirement table was not provided, so the package supplies a complete baseline requirement table. If existing HR requirements must remain authoritative, adapt the service to their verified fields before rollout; merely creating this baseline will not copy existing jobs.

The X++ files are pasteable source, **not an importable compiled model or deployable package**. No F&O compiler, database synchronization, live D365 credentials, or D365 deployment is available in this repository. Build and live acceptance in your F&O environment remain required.

## 1. Files and final objects

| File | What to create/use |
| --- | --- |
| [TABLES.md](TABLES.md) | Exact EDTs, enum values, four tables, fields, relations, and indexes |
| [table-specification.json](table-specification.json) | Machine-readable metadata checklist |
| [contracts-manifest.json](contracts-manifest.json) | Six operations, request parameter names, DTO members, and response shapes |
| [xpp/](xpp/) | Eight data-contract classes and the service class; one file per class |
| [UBHRPortal.postman_collection.json](UBHRPortal.postman_collection.json) | Six ready-to-import POST requests with fictional examples and a blank token |
| [examples/README.md](examples/README.md) | Request/response examples and test order |
| [backend.env.example](backend.env.example) | Copyable D365 settings for the new service group |
| [validate_bundle.py](validate_bundle.py) | Static metadata checks and six mocked calls through the actual FastAPI D365 adapter |
| [../docs/d365-endpoints.md](../docs/d365-endpoints.md) | Backend wire contracts and mapping rules |
| [../docs/d365-schema.md](../docs/d365-schema.md) | Business relationships and persistence order |

Create these eight data-contract classes, followed by the service class:

1. `UBHRPortalRequestContract`
2. `UBHRPortalEvaluationContract`
3. `UBHRPortalRequirementContract`
4. `UBHRPortalApplicationContract`
5. `UBHRPortalResultContract`
6. `UBHRPortalRequirementsContract`
7. `UBHRPortalCandidatesContract`
8. `UBHRPortalApplicationsContract`
9. `UBHRPortalService`

The application contract references the evaluation contract; the collection contracts reference their row contracts. Create all classes before a full build. Helpers are private methods within `UBHRPortalService`; there is no separate helper class to create.

The AOT service also has the name `UBHRPortalService`; the class and service are different metadata element types and can share that name. Create service group `UBHRPortalServiceGroup`. The group contains that AOT service.

| Object type | Exact objects |
| --- | --- |
| Tables | `UBHRJobRequirement`, `UBHRCandidate`, `UBHRJobApplication`, `UBHRMatchEvaluation` |
| Base enums | `UBHRJobStatus`, `UBHRAIStatus`, `UBHRHRStatus` |
| Custom EDTs | 22 shared EDTs listed in TABLES.md; also reuse standard `Notes`, `RefRecId`, and `NoYes` |
| Security | `UBHRPortalIntegrationPrivilege`, `UBHRPortalIntegrationDuty`, `UBHRPortalIntegrationRole` |

## 2. Prepare Visual Studio and a model

Use an F&O developer VM or a supported unified development environment with the **Dynamics 365 Finance and Operations Visual Studio extension** and the matching application/platform metadata. An ordinary Visual Studio 2022 installation on a laptop cannot build X++ tables/services by itself. Some older F&O images use a different supported Visual Studio version; use the version supported by your environment rather than copying its metadata into an unrelated installation.

1. Open the environment's supported Visual Studio instance. If required by that developer VM, run it as administrator.
2. Open **Dynamics 365 → Model management → Create model**. Menu names can vary with the installed extension.
3. Set the model name to `UBHRRecruitmentPortal`, publisher to your organization, and version to your team's initial version. Create a new package for an isolated implementation.
4. Add references to the platform/application packages that expose the standard `Notes`, `RefRecId`, `NoYes`, system services, and application types used here. Usually this includes `ApplicationPlatform`, `ApplicationFoundation`, and `ApplicationSuite`; select the packages available in your environment and avoid unnecessary references. Do not overlay standard Microsoft objects.
5. Select **File → New → Project**, then the installed Dynamics 365 Finance and Operations project template. Name the project `UBHRRecruitmentPortal` and select the model just created in the project's properties.
6. Keep all new EDTs, enums, tables, classes, service, service group, and security objects in this model. Check the project's model property before adding elements.
7. The service uses the platform's `System` and `Newtonsoft.Json` .NET types. If the compiler cannot resolve them, add the supported assembly references already provided with your F&O platform using the project's References node. Do not copy a random NuGet version into the AOS bin directory.

An existing customer model can be used instead if that is your team's established extension strategy. Preserve the exact object/field names in this package unless you also change every reference in the source and configuration.

## 3. Create EDTs, enums, tables, indexes, and relations

Follow [TABLES.md](TABLES.md) in order. Its detailed field grids are the source of truth for this source pack.

1. Right-click the project → **Add → New item** and choose the appropriate **Extended Data Type** template. Create each EDT with the specified base type, string size, and label. Reuse the provided EDT across all matching identifier/reference fields.
2. Add each **Base Enum** listed there and its elements in the exact documented order. The service uses the named enum elements. Enum values are internal metadata; the JSON service returns readable status labels and real JSON booleans.
3. Add each **Table**. Set `SaveDataPerCompany=Yes`, use a regular persistent table, and enable the documented creation/modification timestamps. Do not create `RecId`, `DataAreaId`, or enabled system timestamp fields manually; F&O supplies them.
4. Under the table's Fields node, add every documented field with the appropriate EDT/enum reference. Long JSON, JD, and evidence text uses the unbounded `Notes` memo EDT. Do not replace it with a bounded string that silently truncates a resume comparison.
5. Under Indexes, add the documented indexes. Create their fields in the listed order and set uniqueness/alternate-key properties exactly as specified. `SaveDataPerCompany=Yes` provides the company scope; do not manually add `DataAreaId` to every index.
6. Under Relations, add the documented `RecId` relations. Application links to candidate and requirement; evaluation links to application and requirement. Use the documented cardinality and related-table fields.
7. Save all elements. Inspect the machine-readable [table-specification.json](table-specification.json) against the project before building.

Uniqueness indexes are part of the write protocol, not just a performance option. They protect issuer/subject identity, submission idempotency, stable IDs, and one current evaluation per application when concurrent requests or retries occur.

## 4. Paste the X++ classes

For each `.xpp` file in [xpp/](xpp/):

1. Right-click the project → **Add → New item → Class**.
2. Give the class the exact filename without `.xpp`, for example `UBHRPortalRequestContract`.
3. Open the class in the X++ code editor.
4. Replace the generated empty class text with the **entire contents** of its matching source file, including attributes, declaration, braces, and methods. Do not paste one complete class inside another class's braces.
5. Save it. Repeat for all eight contracts, then `UBHRPortalService`.
6. Build the project/model and resolve compiler errors before creating the service operation links.

The `[DataContract]`/`[DataMember]` attributes define the case-sensitive JSON names. Collection attributes declare the list element classes. All request-bearing methods have the single parameter named **`_request`**. `getOpenRequirements()` is parameterless. Do not rename these parameters without updating the backend wrapper configuration.

The service assigns stable candidate/application/evaluation identifiers, checks the company's legal-entity context, validates referenced jobs/records, and saves candidate/application/evaluation records in transactions. It does not run Azure OpenAI or parse PDF/DOCX in X++.

## 5. Create the AOT service and service group

1. Add a **Service** metadata element named `UBHRPortalService`.
2. In its Properties pane set the **Class** property to the class `UBHRPortalService`.
3. Under Operations, use **Add operation** and select these six public methods. If your extension presents **New operation**, set the method reference using the method selector.

| AOT operation / method | Request body | Return contract |
| --- | --- | --- |
| `getOpenRequirements` | `{}` | `UBHRPortalRequirementsContract` |
| `submitApplication` | `{"_request": {...}}` | `UBHRPortalResultContract` |
| `saveCandidateEvaluation` | `{"_request": {...}}` | `UBHRPortalResultContract` |
| `getTopCandidates` | `{"_request": {...}}` | `UBHRPortalCandidatesContract` |
| `getMyApplications` | `{"_request": {...}}` | `UBHRPortalApplicationsContract` |
| `getApplication` | `{"_request": {...}}` | `UBHRPortalApplicationContract` |

4. Save the service. Expose only these public entry points, not private helper methods.
5. Add a **Service Group** named `UBHRPortalServiceGroup`.
6. Set `AutoDeploy=Yes` where that property is available on your platform.
7. Add a service reference to the AOT service `UBHRPortalService` under the group's Services node. Keep the reference/node name exactly `UBHRPortalService`, because that name forms the middle service path segment. Selecting the class alone is insufficient; the group must reference the AOT service element.
8. Save and build. On current F&O platforms custom service groups are deployed through the supported build/deployment process; the old AX WCF configuration workflow is not required. On a developer VM, follow its documented service refresh/restart procedure if a successfully built group has not appeared.

Every operation uses HTTP **POST**, including read operations. The path includes the service-group name, AOT service name, and operation name:

```text
https://<your-fo-host>/api/services/UBHRPortalServiceGroup/UBHRPortalService/getOpenRequirements
https://<your-fo-host>/api/services/UBHRPortalServiceGroup/UBHRPortalService/submitApplication
https://<your-fo-host>/api/services/UBHRPortalServiceGroup/UBHRPortalService/saveCandidateEvaluation
https://<your-fo-host>/api/services/UBHRPortalServiceGroup/UBHRPortalService/getTopCandidates
https://<your-fo-host>/api/services/UBHRPortalServiceGroup/UBHRPortalService/getMyApplications
https://<your-fo-host>/api/services/UBHRPortalServiceGroup/UBHRPortalService/getApplication
```

## 6. Create integration security

The source uses `[SysEntryPointAttribute(true)]`. Its callers require access to the service operations **and** the tables used by those operations. Create a dedicated integration role; assigning System administrator is not necessary for the implemented operations.

1. Add a **Security Privilege** named `UBHRPortalIntegrationPrivilege` to the model.
2. Under its Entry Points, add **Service Operation** entry points for all six operations. Use the designer's object/service-operation picker to select `UBHRPortalService` and the corresponding operation; this avoids depending on a particular extension's textual object-name syntax. Grant permission to invoke each operation (`Invoke` where exposed by the designer). Configure table Read/Create/Update permissions separately as below, then verify actual calls with the dedicated non-administrator integration user.
3. Under the privilege's table permissions, grant these effective permissions:

| Table | Required access |
| --- | --- |
| `UBHRJobRequirement` | Read |
| `UBHRCandidate` | Read, Create, Update |
| `UBHRJobApplication` | Read, Create, Update |
| `UBHRMatchEvaluation` | Read, Create, Update |

4. Grant relevant field access if your organization uses field-level restrictions. No operation needs Delete permission. Requirement editing is an HR administration capability separate from this integration role.
5. Add **Security Duty** `UBHRPortalIntegrationDuty` and reference the privilege.
6. Add **Security Role** `UBHRPortalIntegrationRole` and reference the duty. An existing reviewed integration role can instead reference the new duty.
7. Build and deploy these security objects with the rest of the model.
8. In F&O, create/select the dedicated enabled integration user. Assign `UBHRPortalIntegrationRole` and access to the intended legal entity.
9. Set that integration user's startup/default company to the exact legal entity used in `D365_COMPANY`, for example `USMF` if that is your actual company.

This source pack intentionally supports one configured legal entity. `getOpenRequirements()` reads in the service user's company context. All request-bearing operations require `Company` to equal that context, and do not silently switch company. A token issued successfully does not prove the mapped F&O user has the right startup company or role.

The trusted server identity can read candidate/application records for backend processing. FastAPI separately enforces candidate ownership and HR roles before returning data to a browser. Do not hand this integration identity or its bearer token to a candidate.

## 7. Build, synchronize, and deploy

1. Build the complete model/project with all new metadata and classes. Fix every compiler error.
2. In the **development environment only**, run the Dynamics 365 **Synchronize database** action for the affected model/package after a successful build. The exact menu/build option varies with the installed extension.
3. Verify synchronization succeeds; a successful X++ build does not itself create SQL columns/indexes.
4. Open each table through the developer table browser and check its fields and indexes. Use a synthetic test record, not candidate production data, for initial testing.
5. Confirm the service group is deployed and the security role/privilege appears.
6. For sandbox/production, commit the model metadata to your normal F&O source-control repository and generate a supported deployable package using your team's build pipeline. Deploy through the environment's supported lifecycle process, including database synchronization and approved maintenance procedures.

Do not modify the production database directly, copy DLLs into a production AOS, or run a desktop Visual Studio synchronization against production. This GitHub repository contains source guidance; it cannot deploy a model to your organization's F&O environment.

## 8. Register the Entra application and map it in F&O

This D365 connection uses a server-to-server Entra **client credentials** flow. It is separate from LinkedIn candidate login and the HR application's interactive Entra login.

1. In the Entra tenant that owns your F&O environment, open **App registrations → New registration**. Create a single-tenant application such as `UBHRRecruitmentPortal-D365` according to your organization's policy.
2. Record its Application/client ID and Directory/tenant ID.
3. Under **Certificates & secrets**, create a client secret with a reviewed expiry/rotation policy. Record the secret **value** once into your secure backend secret store; the secret's ID is not its value. The current Python adapter uses a client secret, so a certificate-only registration requires a separate adapter change.
4. In F&O open **System administration → Setup → Microsoft Entra applications**. Some versions still label this page **Azure Active Directory applications**.
5. Add the application's client ID, a descriptive name, and the dedicated integration user's **User ID**. Save.
6. Ensure that mapped user has the role and company access from step 6. The app registration alone does not grant F&O service permissions.
7. The backend requests the scope `https://<your-fo-host>/.default` through MSAL. Use the actual F&O base URL as the resource; do not use Microsoft Graph or the frontend URL as the token audience.

Never paste the D365 secret into React, Vite `VITE_*` variables, a frontend `.env`, GitHub source, screenshots, or browser requests. In local development put it only in ignored `backend/.env`. In a deployed API/worker use the runtime secret store.

## 9. Seed one real open requirement for testing

This baseline has no job-maintenance form or job-creation API. In the development environment, use the table browser or your team's reviewed import/maintenance tooling to add a synthetic open requirement after synchronization.

Populate the requirement table with at least:

- `RequirementId`: a unique value such as `REQ-TEST-001`.
- `JobTitle`: `Full Stack Developer`.
- `JobDescription`: a complete synthetic JD suitable for a test resume.
- `Responsibilities`, `RequiredSkills`, `PreferredSkills`, `RequiredQualifications`, and `RequiredCertifications`: the actual test job's content; optional fields may remain empty.
- `Department`, `JobLocation`, `WorkMode`, and `EmploymentType`: actual synthetic job values using the types documented in TABLES.md.
- `MinimumExperienceYears` / `MaximumExperienceYears`: real numeric requirements if specified. A zero value means zero; do not use it to imply an unavailable number.
- `NumberOfOpenings`: a positive count, for example `1`.
- `JobStatus`: the enum's `Open` element.
- `PublishedDateTime`: current/past UTC; `ClosingDateTime`: a future UTC deadline or the supported empty value for no deadline.
- `RubricVersion`: `v1`; `EvaluationCriteriaJson`: `{}` if there are no extra criteria.

Create it in the integration user's company. Do not manually populate system `RecId` or timestamp fields. The service returns eligible open jobs only and rechecks eligibility inside application submission.

If your current `UBHRApplicationService/getOpenRequirements` reads an existing recruitment table, choose one authoritative requirement source before live deployment. Have the D365 developer adapt the baseline service's table joins/field mapping or extend the verified existing service. Using one table for public jobs and another for application validation produces mismatched requirement IDs.

## 10. Configure backend endpoints

Edit **`backend/.env`**, preserving your existing LinkedIn/HR settings. Replace placeholder credential values locally or inject them at runtime. Do not commit the populated file.

```dotenv
APP_ENV=development
DEMO_MODE=false
D365_ENABLED=true

D365_BASE_URL=https://<your-fo-host>
D365_TENANT_ID=<your-directory-tenant-id>
D365_CLIENT_ID=<your-server-to-server-application-id>
D365_CLIENT_SECRET=<secret-value-from-your-secure-store>
D365_COMPANY=<integration-users-startup-company>
D365_PARAMETER_NAME=_request

D365_REQUIREMENT_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getOpenRequirements
D365_SUBMIT_APPLICATION_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/submitApplication
D365_SAVE_EVALUATION_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/saveCandidateEvaluation
D365_TOP_CANDIDATES_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getTopCandidates
D365_MY_APPLICATIONS_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getMyApplications
D365_APPLICATION_PATH=/api/services/UBHRPortalServiceGroup/UBHRPortalService/getApplication

D365_REQUEST_WRAPPERS={"get_open_requirements":"","submit_application":"_request","save_candidate_evaluation":"_request","get_top_candidates":"_request","get_my_applications":"_request","get_application":"_request"}
D365_REQUEST_FIELD_MAPS={}
D365_RESPONSE_FIELD_MAPS={}

BACKEND_BASE_URL=https://localhost:7242
FRONTEND_BASE_URL=http://localhost:5173
CORS_ALLOWED_ORIGINS=["http://localhost:5173"]
LINKEDIN_REDIRECT_URI=https://localhost:7242/auth/linkedin/callback
```

Use the base F&O origin without `/api/services/...` in `D365_BASE_URL`. The six path variables contain **relative** paths. Reset old field-map omissions/renames only after confirming this exact source pack is deployed; the supplied DTOs use the adapter's default PascalCase field names, including `LinkedInProfileJson`.

Also configure the existing LinkedIn credentials, HR Entra credentials/roles, and these services for the complete connected flow:

```dotenv
REDIS_URL=<private-redis-connection-url>
REDIS_PREFIX=talentmatch

AZURE_STORAGE_CONNECTION_STRING=<private-storage-connection-string>
AZURE_STORAGE_CONTAINER=resumes

AZURE_OPENAI_ENDPOINT=https://<your-azure-openai-resource>/
AZURE_OPENAI_API_KEY=<your-azure-openai-key>
AZURE_OPENAI_DEPLOYMENT=<your-supported-model-deployment>
AZURE_OPENAI_API_VERSION=<api-version-supported-by-that-deployment>
```

Provision a private Blob container and reachable Redis before starting connected mode. Use matching configuration in API and worker. `DEMO_MODE=true` continues to show fixtures and does not write these tables. For production set `APP_ENV=production` and serve both portal and backend through reviewed HTTPS URLs with matching secure origins; the local HTTP frontend example above is development configuration.

## 11. What belongs in the frontend

**No D365 custom-service URL or D365 credential belongs in the frontend.** The browser's existing [frontend/src/lib/api.ts](../frontend/src/lib/api.ts) calls relative FastAPI routes such as `/api/jobs`, `/api/applications`, `/api/me/applications`, and `/api/hr/jobs/{id}/candidates`. FastAPI obtains its D365 token, calls the configured custom service, and returns the authorized portal response.

For your local HTTPS backend on port `7242`, set both proxy targets in **`frontend/vite.config.ts`** to that backend:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "https://127.0.0.1:7242", secure: true },
      "/auth": { target: "https://127.0.0.1:7242", secure: true },
    },
  },
  preview: { port: 5173 },
});
```

The mkcert certificate you created includes `127.0.0.1` and `localhost`. Trust the local CA in Node before starting Vite; restarting is required because Node reads the variable at startup. From the frontend PowerShell window:

```powershell
$mkcertCaRoot = (& "$env:USERPROFILE\Tools\mkcert.exe" -CAROOT).Trim()
$env:NODE_EXTRA_CA_CERTS = Join-Path $mkcertCaRoot "rootCA.pem"
npm run dev
```

Keep TLS verification enabled. Open the frontend using `http://localhost:5173` consistently so login/callback cookies use the same hostname. The LinkedIn developer app's registered callback stays exactly `https://localhost:7242/auth/linkedin/callback`.

Vite's proxy is a development setting. In production the HTTPS ingress/web server must route `/api` and `/auth` to FastAPI, and serve the built React app with a router fallback. See [deployment.md](../docs/deployment.md).

## 12. Start the API and separate worker on Windows

After updating the configuration, stop old API/worker processes before starting them with the new settings. From the API PowerShell terminal:

```powershell
cd "$env:USERPROFILE\Documents\Projects\UB_HRProcess_Agent\backend"
uv sync --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 7242 --ssl-certfile .certs\localhost.pem --ssl-keyfile .certs\localhost-key.pem
```

These paths assume the already generated certificates are in **`backend\.certs`**, as in your current setup. Do not move or commit the private key.

In a second PowerShell terminal, run the worker with the same backend `.env`:

```powershell
cd "$env:USERPROFILE\Documents\Projects\UB_HRProcess_Agent\backend"
uv run --frozen python -m app.worker
```

Keep the frontend running in its separate terminal. The health route is `GET /api/health`, so `https://localhost:7242/health` can return 404 even when the API is healthy. Worker readiness, D365 authorization, and the external services need separate checks.

## 13. Test the six services, then test the portal

Use a trusted server-side test client such as Postman with an Entra client-credentials access token for the F&O resource. Send `Authorization: Bearer <token>` and `Content-Type: application/json`. Keep the token in the test client's secret/auth field; do not add it to source or a browser frontend.

All calls are POST. Use one configured company and synthetic identity/resume metadata throughout. The shapes are defined in [contracts-manifest.json](contracts-manifest.json) and [d365-endpoints.md](../docs/d365-endpoints.md).

1. **getOpenRequirements**: send `{}`. Expect a `Requirements` array containing the synthetic open requirement, with a full `JobDescription` and correct ID.
2. **submitApplication**: send `{"_request": {...}}` with `Company`, `RequirementId`, validated `LinkedInIssuer`/`LinkedInSub`, contact details, consent, a private `ResumeBlobKey`, filename, 64-character `ResumeSha256` and `JDHash` digests, and a unique `IdempotencyKey`. Expect `Success=true` and stable `ApplicationId`/`CandidateId`. Inspect the candidate and application tables. Retrying the identical key must return the same application rather than create another row.
3. **saveCandidateEvaluation**: use the returned application ID, its requirement ID, and the synthetic valid evaluation fields/JSON strings. Expect success and a stable evaluation ID. Verify the separate evaluation table and `AIStatus=Completed` in the application. Repeat the same save and verify one current evaluation row. This test exercises persistence only; the real score comes from the worker.
4. **getTopCandidates**: send `{"_request":{"Company":"<company>","RequirementId":"REQ-TEST-001","Limit":25}}`. Verify the `Candidates` array is scoped to that job and includes the submitted application/evaluation with descending score order. Limit is a top-N cap, not a total population count or pagination.
5. **getMyApplications**: send `{"_request":{"Company":"<company>","LinkedInIssuer":"https://www.linkedin.com/oauth","LinkedInSub":"<same-synthetic-subject>"}}`. Verify only that identity's applications are returned in `Applications`. Test a different synthetic subject returns none.
6. **getApplication**: send `{"_request":{"Company":"<company>","ApplicationId":"<returned-id>"}}`. Verify the complete authorized backend record and its nested `Evaluation`. The backend applies ownership/HR checks before exposing this record to portal users.

In evaluation memo fields, send strings containing valid JSON arrays, for example `"MatchedSkillsJson":"[]"`. Send `LinkedInProfileJson` as a JSON object serialized inside a string, for example `"{\"sub\":\"synthetic-subject\",\"issuer\":\"https://www.linkedin.com/oauth\"}"`. Do not store raw token responses or OAuth tokens.

A fabricated Blob key is suitable only for a service-contract persistence test. It is not a working resume download. The portal acceptance test below must upload a real synthetic document and use the actual backend-generated key, unchanged including its `azure:` prefix.

Then perform a complete portal acceptance test:

1. Read the actual seeded job through the portal with `DEMO_MODE=false`.
2. From that job choose LinkedIn sign-in, confirm return to its application form, and verify available profile fields are shown. Missing LinkedIn email/name remain empty; a member URN is an identity, not an email.
3. Confirm/fill contact details, upload a text-based synthetic PDF/DOCX, accept consent, and submit once.
4. Verify candidate master and application snapshot are saved before any evaluation result exists. Sign-in alone must not create an application.
5. Observe the separate worker compare that uploaded resume against the selected JD through Azure OpenAI, then verify one separate linked evaluation record is saved.
6. Verify candidate history/detail shows only the signed-in candidate's submissions. Sign in as another candidate to test denial of the first candidate's application.
7. Sign in using the configured HR identity/role, inspect job-specific ranking/evidence, and download the authorized original resume. Candidate users must be denied HR routes.
8. Test a closed job, wrong company, invalid request, duplicate submission retry, and transient worker retry. Confirm failures never show fixture success in connected mode.

Application/contact records are committed first. The API then acknowledges the application and queues processing through Redis. X++ saves the evaluation only when the worker has generated and validated it. No AI computation occurs in the service class.

Submission retry keys are immutable: the same key with changed contact/job/document data is rejected. Evaluation persistence keeps one current record per application: the same content is a no-op; changed validated content replaces that record and retains its evaluation ID. This implements the worker's fixed `evaluation:<ApplicationId>` key without fabricating historical versions.

To rerun the source/contract checks without a live D365 environment:

```powershell
cd backend
uv run --frozen python ../d365/validate_bundle.py
```

This checks metadata field references, DTO members/types, all example response models, actual request bodies from the six Python adapter methods, and the Postman collection. It does not compile X++ or verify the live AOT service serializer/security.

## 14. Common setup errors

| Symptom | Check |
| --- | --- |
| X++ class/type not found | Exact class name, model references, all eight contracts present, and successful model build |
| Unknown table/field/enum element | TABLES.md metadata names/properties and the model containing them; do not substitute an unrelated table without adapting all code |
| `Newtonsoft.Json` type unresolved | Supported platform assembly reference in the F&O development project/model |
| SQL column/index does not exist | Successful development database synchronization after the metadata build |
| Custom service 404 | Exact group/service/operation path, service reference under the group, six exposed operations, successful deployment/service refresh |
| Custom service 401 | Correct F&O token resource, tenant/client/secret value and expiry, exact base URL, and F&O Entra application registration |
| Custom service 403/access denied | Mapped F&O user's enabled status, role/duty/privilege, service-operation entry points, and table permissions |
| Company validation error or no jobs | `D365_COMPANY` equals the integration user's startup company; seeded job exists in that company and is currently eligible |
| Empty/null request contract | `_request` must exactly match the X++ parameter name; parameterless jobs use `{}` |
| Old jobs remain fictional | `DEMO_MODE=false` and API restarted with the backend `.env`; new endpoints actually deployed |
| Application saved but evaluation pending | Separate worker running, shared Redis/config, private Blob reachable, Azure OpenAI configured, save-evaluation endpoint reachable |
| Vite cannot verify first certificate | `NODE_EXTRA_CA_CERTS` points at mkcert `rootCA.pem` before restarting Vite |
| Port 7242 already in use | Stop the previous local backend before restarting it; keep the configured port and registered callback consistent |

Processing/retry failures are coordinated in Redis. These six operations save pending application state and completed evaluations; they do not implement a separate D365 Processing/Failed update, HR status write, job-maintenance form, historical evaluation versioning, or deletion/retention service. Those are additional reviewed business capabilities, not hidden operations to call from the frontend.

Microsoft's platform references: [custom service JSON endpoints and automatic service-group deployment](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/custom-services), [service authentication and F&O Entra application/user mapping](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/services-home-page).
