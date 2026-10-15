# Candidate and HR authentication

Authentication is handled by FastAPI. Candidates use `/auth/linkedin/login`. The HR form posts username/password to `/api/auth/hr`, where they are compared with backend environment credentials. The frontend does not exchange authorization codes, persist credentials, or receive D365 tokens.

## LinkedIn candidates

Enable **Sign In with LinkedIn using OpenID Connect** for the LinkedIn developer application. Configure these backend variables:

```dotenv
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=https://localhost:7242/auth/linkedin/callback
LINKEDIN_ISSUER=https://www.linkedin.com/oauth
LINKEDIN_DISCOVERY_URL=https://www.linkedin.com/oauth/.well-known/openid-configuration
```

The connected local deployment uses this exact registered HTTPS callback. Keep scheme, localhost host, port 7242 and path unchanged. If browsing through a same-origin proxy, register the externally visible callback; the internal container hostname is not a browser callback. Production callbacks must use HTTPS.

The application requests the fixed required scopes `openid profile email`. There is no configurable scope variable that pretends to enable extra LinkedIn data. Those scopes provide basic identity only; phone numbers, profile URLs, employment history, projects, and skills are not guaranteed. Optional contact information comes from the application form; work evidence comes from the uploaded resume.

Authlib performs the authorization-code exchange using `client_secret_post` and validates the ID token's signature through provider discovery/JWKS, the configured issuer, registered audience, expiry, and any access-token hash. LinkedIn may omit `nonce` from authorization-code ID tokens. A LinkedIn-specific claims validator allows only that omission; any returned nonce must match the session challenge. Session-bound OAuth state and the single-use backend code exchange remain required. Microsoft Entra still requires a matching nonce.

After validating the ID token, the backend retrieves LinkedIn's user-info response and requires its subject to exactly match the signed token's subject. Only profile/contact fields are copied; user-info cannot replace validated identity claims. Missing user-info fields do not erase profile data already present in the signed token. The candidate is identified by the validated issuer/subject, never by name or email.

LinkedIn profile name, email, and `email_verified` are optional. A subject-only profile can sign in with empty contact fields; the backend does not invent a name or email address. The application form prefills available profile data and requires the candidate to confirm a full name and valid contact email before submission. Contact details can be edited, are not used for authorization, and are not presented as verified by LinkedIn. Microsoft Entra's required profile information and HR role checks remain strict.

State and the nonce challenge are kept in the backend session. An invalid, replayed, or unverifiable callback fails; raw token responses are not logged. Callback diagnostics contain only the provider, exception class, and allowlisted error/claim identifiers. On successful login the backend rotates the opaque session identifier and CSRF token.

## Return to the selected job

The selected-job sign-in link uses `/auth/linkedin/login?return_to=%2Fjobs%2FREQ-2026-001%2Fapply`. The backend saves the validated return path with that authorization attempt's OAuth state. After a successful callback, it redirects to the configured frontend origin plus the saved path. A callback query cannot replace that saved destination. Only allowed relative routes for the signing-in role are accepted; external URLs, encoded traversal, controls, backslashes, and authentication routes are rejected.

An anonymous candidate who starts applying for a job returns to that same job's application form. The general Sign in link preserves the current job page, including its query and fragment. A sign-in without a requested destination retains the candidate applications or HR workspace default. The LinkedIn developer application's registered callback URI remains the backend `/auth/linkedin/callback`; the frontend destination does not change that registration.

## Profile response and application data

The browser callback contains `code` and `state`. FastAPI exchanges the code on the backend, validates the identity token, and reads LinkedIn user-info. `GET /api/auth/me` returns the sanitized candidate identity and optional `user.linkedin_profile` object:

```json
{
  "sub": "example-linkedin-subject",
  "issuer": "https://www.linkedin.com/oauth",
  "name": "Alex Example",
  "given_name": "Alex",
  "family_name": "Example",
  "email": "alex@example.com",
  "email_verified": true,
  "picture": "https://media.licdn.com/dms/image/example",
  "locale": "en-IN"
}
```

This is an illustrative public-profile object, not a guaranteed LinkedIn response. Unavailable optional fields are null. The form displays only available name, given/family name, valid email and its supplied verification status, permitted HTTPS LinkedIn photo, locale, and the separate account identifier. An opaque identifier such as `urn:li:member:...` is never an email prefill or an inferred public profile URL. Provider access/ID/refresh tokens and arbitrary raw claims are not included.

Before submission, the candidate confirms the editable full name and contact email, fills optional phone/profile URL, uploads a resume, and accepts consent. The authenticated issuer/subject remain fixed. The lean D365 submission includes confirmed contact fields and verified identity; the sanitized provider-profile snapshot remains in portal metadata. Candidate/application persistence must complete before an `ApplicationId` is acknowledged and evaluation is queued. The worker saves resume/JD matching results through the separate evaluation service, linked by that identifier. See [D365 contracts](d365-endpoints.md).

## HR username/password

Configure `HR_USERNAME` and `HR_PASSWORD` in native `backend/.env`, portable Docker root `.env`, or backend runtime secrets, then restart the API. Both must be set; there is no default account. Enter them on `/hr/login`. Matching is exact and case-sensitive; the username is not required to be a public email address.

The backend checks both credentials, assigns the HR role, and rotates the opaque session and CSRF token. Existing HR API and private resume authorization checks apply. `HR_LOGIN_RATE_LIMIT` defaults to five attempts per client per minute. Missing configuration returns 503; incorrect credentials return a generic 401. Credentials are excluded from terminal logs and browser storage. D365's service-app credentials are separate and remain required.

## Optional legacy Microsoft Entra HR users

The older HR OIDC endpoints remain available for deployments that explicitly configure them; the current HR sign-in page uses username/password and does not link to Microsoft. To use the legacy endpoints, create a tenant-specific web application registration with an authorization-code callback. Configure:

```dotenv
HR_ENTRA_TENANT_ID=
HR_ENTRA_CLIENT_ID=
HR_ENTRA_CLIENT_SECRET=
HR_ENTRA_REDIRECT_URI=http://localhost:8000/auth/hr/callback
HR_ALLOWED_ROLES=["HRRecruiter","HRAdministrator"]
ENTRA_HR_ROLE=TalentMatch.HR
```

Define application roles in the registration and assign approved HR users/groups in the enterprise application. The backend validates tenant-specific issuer and tenant ID, then requires a token `roles` claim matching the configured allowlist or `ENTRA_HR_ROLE`. Ensure **both** settings reflect your intended policy; the singular role is also accepted. A normal signed-in user without an allowed application role receives a forbidden response. The registration for interactive HR login may be separate from the D365 service application's client credentials.

The backend requires a profile name and email or `preferred_username`. Do not replace application-role checks with email-domain checks or rely on hiding the React HR routes. Backend dependencies protect every HR API and resume route.

## Sessions and CSRF

Cookies contain an unpredictable random session identifier, not identity claims or OAuth tokens. Connected mode stores sessions in Redis with `SESSION_TTL_SECONDS`; local demo mode uses process-local state. Cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when `APP_ENV=production`. A `SESSION_SECRET` is not required because no signed identity/session payload is placed in a client-side cookie.

`GET /api/auth/me` returns the current user and CSRF token. The API client includes `X-CSRF-Token` in state-changing requests. FastAPI checks the token and an allowed browser Origin when present. Logout clears the authenticated session and rotates its state. Use a same-origin HTTPS deployment for reliable OAuth and cookie behavior.

## Demo authentication

`POST /api/auth/demo` accepts the explicit candidate or HR demo role only with `DEMO_MODE=true` and `APP_ENV=development`; it is CSRF-protected. Demo identities and scores are labeled fixtures. The production configuration validator rejects demo mode. Switching to connected mode never silently substitutes demo authentication.

## Diagnose configuration failures

| Symptom | Check |
| --- | --- |
| Provider configuration error | Backend client ID/secret and Entra tenant are present; restart after configuration changes |
| Redirect mismatch | Registered URI equals the externally visible configured callback exactly |
| Invalid callback/state | Login and callback use the same browser cookie, Redis session, host, and HTTPS/proxy setup |
| `MissingClaimError` for LinkedIn `nonce` | Update the backend to the LinkedIn code-flow compatibility fix; restart and begin a fresh login |
| Generic callback 401 | Read the sanitized `OIDC callback failure` line in backend logs; never share token responses or credentials |
| HR forbidden | Correct tenant token and assigned allowed application role are present |
| LinkedIn name/email unavailable | Sign in with the validated subject and complete the required contact fields when applying |
| Session service unavailable | Connected API can reach its private Redis instance and persist sessions |

Validate provider registration and real consent/login with configured accounts before production use. Automated tests exercise mocked callback/authorization behavior; they do not establish a working live provider registration.
