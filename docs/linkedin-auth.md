# Candidate and HR authentication

Authentication is handled by FastAPI. The frontend redirects the browser to `/auth/linkedin/login` or `/auth/hr/login`; it does not exchange authorization codes, store provider credentials, or receive D365 tokens.

## LinkedIn candidates

Enable **Sign In with LinkedIn using OpenID Connect** for the LinkedIn developer application. Configure these backend variables:

```dotenv
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=http://localhost:8000/auth/linkedin/callback
LINKEDIN_ISSUER=https://www.linkedin.com/oauth
LINKEDIN_DISCOVERY_URL=https://www.linkedin.com/oauth/.well-known/openid-configuration
```

The localhost URI is a local example. Enter the **exact** redirect URI already registered for your application, including scheme, host, port, and path. If browsing through a same-origin proxy, register the externally visible callback; the internal container hostname is not a browser callback. Production callbacks must use HTTPS.

The application requests the fixed required scopes `openid profile email`. There is no configurable scope variable that pretends to enable extra LinkedIn data. Those scopes provide basic identity only; phone numbers, profile URLs, employment history, projects, and skills are not guaranteed. Optional contact information comes from the application form; work evidence comes from the uploaded resume.

Authlib performs the authorization-code exchange using `client_secret_post` and validates the ID token's signature through provider discovery/JWKS, the configured issuer, registered audience, expiry, and any access-token hash. LinkedIn may omit `nonce` from authorization-code ID tokens. A LinkedIn-specific claims validator allows only that omission; any returned nonce must match the session challenge. Session-bound OAuth state and the single-use backend code exchange remain required. Microsoft Entra still requires a matching nonce.

After validating the ID token, the backend retrieves LinkedIn's user-info response and requires its subject to exactly match the signed token's subject. Only profile name, email, and `email_verified` are copied; user-info cannot replace validated token claims. The backend requires `email_verified=true` and identifies the candidate by the validated issuer/subject. Missing or inconsistent profile data fails visibly rather than creating an assumed identity.

State and the nonce challenge are kept in the backend session. An invalid, replayed, or unverifiable callback fails; raw token responses are not logged. Callback diagnostics contain only the provider, exception class, and allowlisted error/claim identifiers. On successful login the backend rotates the opaque session identifier and CSRF token. The browser returns to the candidate application workspace.

## Microsoft Entra HR users

Create a tenant-specific web application registration with an authorization-code callback. Configure:

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
| Missing LinkedIn profile | OIDC product/scopes enabled and required verified name/email claims returned |
| Session service unavailable | Connected API can reach its private Redis instance and persist sessions |

Validate provider registration and real consent/login with configured accounts before production use. Automated tests exercise mocked callback/authorization behavior; they do not establish a working live provider registration.
