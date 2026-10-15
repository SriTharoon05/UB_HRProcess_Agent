# IT request: Phase 1 Azure container deployment

The requested deployment is **one Linux App Service container**, pulled from the company Azure Container Registry. The image runs React static files/Nginx, FastAPI, the existing ARQ worker, and localhost Redis under Supervisor. PostgreSQL and private Blob storage hold durable records and files. This is Phase 1 recruitment intake and evidence review; later screening, interviews and onboarding remain separate phases.

## Resources and decisions to request

| Request | Required configuration / reason |
| --- | --- |
| Company GitHub repository | Private, empty repository owned by the company organization; `main` branch, Actions enabled, environment named `production`, reviewers and protected-branch policy |
| Azure resource group | Company subscription, approved region, owner, cost center and tags; separate production/development resources where required |
| Azure Container Registry | Company ACR, admin credentials disabled; standard registry RBAC for this guide; Basic/Standard for approved public access, Premium if private endpoints are required |
| Linux App Service plan | Pilot: B2 or better after load validation; recommended production starting point P1v3 or equivalent approved SKU. **Exactly one instance**, Always On; no autoscale while using bundled Redis |
| Linux Web App for Containers | Classic custom single-container configuration, image from ACR, container target port **8080**, HTTPS Only, TLS 1.2+, Health Check `/healthz`, startup timeout 600 seconds |
| App Service managed identity | System-assigned identity; `AcrPull` on ACR and `Key Vault Secrets User` on the approved vault. Enable managed-identity registry pulls; no ACR password in settings |
| GitHub deployment identity | Dedicated Entra application/service principal or user-assigned managed identity with **GitHub OIDC federation**, restricted to `repo:COMPANY/REPOSITORY:environment:production`; `AcrPush` on ACR and `Website Contributor` on this Web App |
| Key Vault | Store the HR password, database connection URI, LinkedIn client secret, D365 client secret, OpenAI key and private Blob connection string; IT owns rotation and App Service reference permissions |
| PostgreSQL | Approved Supabase project **or** Azure Database for PostgreSQL Flexible Server; connection string, verified TLS and backup policy. Current Azure image requires PostgreSQL metadata; keep `D365_CONTRACT_MODE=sqlite` for the lean ERP contract |
| Private Azure Blob | Company storage account and a private `talentmatch-resumes` container (or approved existing name); lifecycle/backup/access policy; current implementation reads a server-side connection string from Key Vault |
| Azure AI Foundry / Azure OpenAI | Dedicated company resource/project and **model deployment**, as detailed below; approved region and token quota |
| D365 integration identity | Company-owned Entra client credentials; registered in F&O, correct legal entity, permission to the existing three custom-service operations and four tables |
| LinkedIn developer application | Company-owned application with the OIDC sign-in product, approved administrator, client credentials and permission to register the final public HTTPS callback |
| Public hostname / TLS | Actual App Service default hostname or approved custom domain and managed certificate; return the exact HTTPS origin to the developer |
| Monitoring | Container stdout/stderr, health alerts, restart/CPU/memory alerts, deployment ownership, budgets and backup/restore owners. Avoid collecting OAuth query strings or raw resume/provider payloads |
| Network / CI runners | Allow ACR pulls and outbound HTTPS to LinkedIn, Entra, D365, OpenAI, Blob, Key Vault and approved PostgreSQL endpoint. Private ACR/Web App requires a company runner with the required network reach; GitHub-hosted runners cannot reach arbitrary private endpoints |

These SKUs are sizing proposals, not cost or capacity guarantees. IT should confirm region availability, company policy and measured workload before purchase. Enabling ACR repository ABAC changes the required registry roles: use the corresponding Repository Reader/Writer roles and repository catalog access rather than applying `AcrPull`/`AcrPush` blindly. The deployment commands below assume ordinary registry RBAC.

## Foundry request: a separate deployment, not model training

Request a dedicated deployment such as **`talentmatch-evaluation`**, initially backed by **GPT-4.1-mini** if approved and available in the selected region. This uses an existing hosted model; it does not require training or fine-tuning a new model. A separate deployment gives this project its own deployment name, quota allocation, usage tracking and model-version lifecycle.

Required model capabilities:

- Azure OpenAI **Chat Completions**, system/user messages, structured JSON-schema output, and SDK `beta.chat.completions.parse` compatibility.
- Support for `temperature=0.1`; do not substitute a reasoning deployment with incompatible parameters without updating and validating the code.
- Context capacity for the complete JD, resume and response schema. Resume input is guarded at 100,000 characters; actual token limits still apply.
- An initial quota proposal of 50,000 TPM, or a workload-approved alternative with the corresponding RPM limit. IT must confirm available capacity and cost; retries handle 429 throttling but do not create quota.

IT should provide the resource endpoint, actual **deployment name**, supported API version, model/version/region and quota. The existing configurable API version is `2025-03-01-preview`; approve that version or validate a compatible approved version with structured output. Use an Azure OpenAI resource endpoint compatible with `AsyncAzureOpenAI`, not a generic Foundry project URL or an unrelated model inference endpoint.

The current client uses an API key held in Key Vault. Grant developers the scoped permission needed to create/manage approved model deployments (for an Azure OpenAI resource, typically `Cognitive Services OpenAI Contributor`). Assigning an inference role to App Service alone does not switch this application's key-based SDK to Entra authentication.

## Values IT should return

Return these **non-secret** deployment values: subscription ID, tenant ID, resource group, registry name/login server, Web App name, actual public hostname, deployment identity client ID, approved region, Key Vault name, model deployment/API version, Blob account/container, PostgreSQL host/port, and private-runner label if needed.

Provide credentials through Key Vault or the company's secure secret channel, not a GitHub issue, email attachment, Dockerfile or frontend `VITE_*` variable. Complete the environment settings in [the Azure deployment guide](azure-app-service.md).

## Single-container operating boundary

The bundled Redis binds only to loopback and uses the container's temporary filesystem. It survives a Redis process restart inside the same container, but **does not promise persistence across App Service container replacement**. Users may need to sign in again; durable PostgreSQL outbox records recover pending work and Blob retains original documents. PostgreSQL is not a replacement for Redis sessions.

Run one active instance and serialized deployments. Before high availability, autoscale or concurrent production slots, approve a shared managed Redis service and configure the same `REDIS_URL`/prefix across instances. The existing PostgreSQL evaluation lock adds protection but does not make independent local Redis sessions distributed. A managed service can be Azure Managed Redis or another company-approved Redis-compatible service; verify its TLS/database/authentication options against the ARQ/redis client before adopting it.

App Service fronts this image with public HTTPS on port 443 and forwards HTTP internally to port 8080. **No mkcert certificate and no public port 7242 are required in Azure.** Local Docker remains at `https://localhost:7242` with its existing separate configuration.

## Suggested request message

> Please provision the company-owned Phase 1 recruitment environment described above: private GitHub repository with protected main and production approval, ACR, one Linux container App Service, OIDC deployment identity, App Service managed identity, Key Vault, PostgreSQL, private Blob, and a dedicated Azure OpenAI model deployment. Please return the non-secret resource names/IDs, final HTTPS hostname and approved network/runner configuration, and supply integration secrets through Key Vault. The initial container embeds Redis and must stay single-instance; shared managed Redis is required before scale-out. The application uses existing D365 recruitment services and requires LinkedIn OIDC registration for the final callback URL.
