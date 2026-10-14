# JSON contract examples

These files contain **fictional data**, not recorded LinkedIn, Azure OpenAI, Azure Blob, or D365 responses. Each of the six operations has a `.request.json` and `.response.json` file. The examples match the DTO names and DataMember types in [contracts-manifest.json](../contracts-manifest.json).

All operations use HTTP **POST** and `Content-Type: application/json`. The service path is:

```text
https://YOUR-ENVIRONMENT.operations.dynamics.com/api/services/UBHRPortalServiceGroup/UBHRPortalService/OPERATION
```

`getOpenRequirements` accepts `{}` and reads the F&O integration user's default company. Set that default company to the same legal entity as `D365_COMPANY`. The other five operations accept `{ "_request": { ... } }` and explicitly receive `Company`.

| Operation | Request example | Response example |
| --- | --- | --- |
| `getOpenRequirements` | [request](getOpenRequirements.request.json) | [response](getOpenRequirements.response.json) |
| `submitApplication` | [request](submitApplication.request.json) | [response](submitApplication.response.json) |
| `saveCandidateEvaluation` | [request](saveCandidateEvaluation.request.json) | [response](saveCandidateEvaluation.response.json) |
| `getTopCandidates` | [request](getTopCandidates.request.json) | [response](getTopCandidates.response.json) |
| `getMyApplications` | [request](getMyApplications.request.json) | [response](getMyApplications.response.json) |
| `getApplication` | [request](getApplication.request.json) | [response](getApplication.response.json) |

`Success`, `ConsentAccepted`, and `MeetsMinimumCriteria` are JSON booleans. Dates are ISO 8601 UTC strings. Evidence fields are JSON **strings containing arrays**, so the quotes inside them are escaped in the outer JSON. `LinkedInProfileJson` is a JSON string containing an object with the original allowlisted OIDC keys. A pending application has `Evaluation: null`, not an invented zero score. Status values are the English contract names, not translated labels or enum integers.

The profile snapshot is separate from editable application contact details. A LinkedIn subject is not an email address. Do not place access tokens, ID tokens, refresh tokens, or session cookies in any memo field.

The example `azure:...pdf` value is a private object reference only; this request does not upload that object. The example document hash and JD hash are illustrative. For a complete portal test, submit a real document through the portal so the backend generates its storage reference, document checksum, JD context hash, identity, and evaluation. Do not use these fixture values to claim successful private resume retrieval or a genuine AI comparison.

The response files show possible successful shapes. IDs and timestamps are assigned by the service, so live values will differ. The pending second application in the history/ranking fixtures demonstrates nullable evaluation handling; the six example requests do not create it automatically. Repeated submissions are transport-idempotent only when the same persisted request key and identical payload are reused. A business rule about revised applications is a separate policy.

## Postman setup

1. Import [UBHRPortal.postman_collection.json](../UBHRPortal.postman_collection.json).
2. Set the collection's `foBaseUrl` to your actual F&O HTTPS resource URL, without a trailing slash. Set `company` to the integration user's default company and `requirementId` to an existing open requirement in that company.
3. Acquire an Entra client-credentials access token locally for the scope `<F&O resource URL>/.default`. The application's client ID must be registered against the correctly authorized F&O integration user. This is a D365 resource token, separate from a candidate's LinkedIn sign-in.
4. Put the token in a **local, sensitive** `accessToken` value in Postman. The exported collection deliberately contains no token or client secret. Do not share exports containing credential values.
5. In an F&O development environment, replace the fictional identity/contact/document values as needed. `resumeBlobKey`, `resumeSha256`, and `jdHash` must describe the intended test document/context. Update `submitIdempotencyKey` to a new stable key for a genuinely new application; reuse it with the identical body when testing a retry.
6. Run `getOpenRequirements`, then `submitApplication`. Its Postman test stores the returned `ApplicationId` in `applicationId`; the service-generated ID replaces the fictional example ID for the remaining requests.
7. Run `getApplication` and `getMyApplications` to confirm that the application has the expected requirement, immutable owner, contact snapshot, and pending evaluation. Do not run `saveCandidateEvaluation` until an application exists.
8. The supplied `saveCandidateEvaluation` body is a fictional contract test. In a development-only test, it checks persistence and serialization. In connected portal use, the worker sends the actual validated Azure OpenAI result. Run it, then `getTopCandidates` and `getApplication` to verify the saved evaluation.
9. Repeat submit with the same key/body and confirm the same `ApplicationId` with no additional candidate/application. Repeat save and confirm one current evaluation for that application. These are live checks to perform in your F&O development environment; the repository fixtures do not prove that deployment succeeded.

Postman inherits bearer authentication from the collection. Leave SSL verification enabled and use the environment's trusted HTTPS certificate. A custom-service request rejection should be investigated as a deployment, identity, permission, company, or contract issue; the fixture response is not a replacement for the live response.
