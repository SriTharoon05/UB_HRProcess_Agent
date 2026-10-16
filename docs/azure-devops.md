# Azure DevOps → ACR → App Service

Use personal GitHub temporarily as the source of changes, pull those commits locally, then push them to **Azure Repos Git**. Azure Pipelines builds the application, stores its image in Azure Container Registry (ACR), and deploys it to Linux App Service.

```text
Personal GitHub → local Git checkout → company Azure Repos Git
                                      ↓
                               Azure Pipelines
                                      ↓
                               ACR image repository
                                      ↓
                               Linux App Service
```

This guide uses the root [azure-pipelines.yml](../azure-pipelines.yml) and [Dockerfile.azure](../Dockerfile.azure). The single image runs React/Nginx, FastAPI, the ARQ worker, and Redis. The portable local Docker package remains separate. Complete the one-time Azure DevOps configuration below before the first real pipeline run; adding these files does not create or deploy company resources.

**Before deployment:** Supabase migration is already complete; do not migrate it again. Azure production currently requires `DATABASE_SSLMODE=verify-full`. Your local `DATABASE_SSLMODE=require` setting will fail the Azure image's production startup checks. Configure the trusted database certificate chain before enabling deployment; instructions are below.

The steps assume **Azure DevOps Services and a Git repository**, not TFVC. Older on-premises TFS/Azure DevOps Server may need a self-hosted agent and a different service-connection setup.

## 1. Obtain the existing Azure resources and scoped access

Use existing company resources where approved. Obtain their actual names and IDs:

| Item | Required setup |
| --- | --- |
| Azure DevOps project | Azure Repos Git, Pipelines, permission to create a variable group, service connection and deployment environment |
| ACR | Registry name and login server; image repository will be `talentmatch-portal` |
| Linux App Service | Resource group, Web App name and exact public HTTPS hostname |
| Pipeline identity | Azure Resource Manager service connection using workload identity federation; registry `Reader` plus `AcrPush`, and `Website Contributor` scoped to this Web App |
| Web App managed identity | `AcrPull` on ACR; `Key Vault Secrets User` on the approved vault when using Key Vault references |
| Agent | Microsoft-hosted Ubuntu agent capacity, or a company Linux agent with Docker, Azure CLI and access to the required resources |

The ACR roles above assume ordinary registry RBAC. If ACR uses **RBAC Registry + ABAC Repository Permissions**, IT must assign the corresponding `Container Registry Repository Writer` to the pipeline identity and `Container Registry Repository Reader` to the Web App identity, with appropriate repository scope. Keep management-plane `Reader` for registry discovery. Legacy `AcrPush`/`AcrPull` are not the correct repository permissions in that mode.

The developer does not need subscription Owner. IT can create the identities and role assignments. A private registry or private Web App requires an agent and App Service networking/DNS that can reach them; a public hosted agent cannot reach arbitrary private endpoints.

## 2. Copy the committed code to an empty Azure Git repository

In Azure DevOps, create a private Git repository without an initial README or other commit. Copy its HTTPS clone URL from **Repos → Files → Clone**.

From your existing Windows project folder:

```powershell
cd C:\Users\sritharoon.as\Documents\Projects\UB_HRProcess_Agent
git pull --ff-only origin main
git status --short
git remote -v
git remote add company "PASTE_THE_AZURE_DEVOPS_GIT_CLONE_URL"
git push company main
```

Use the company-approved Git sign-in. If `company` already exists, inspect `git remote -v` and update it with `git remote set-url company "EXACT_CLONE_URL"` if necessary.

`origin` remains personal GitHub; `company` points to Azure DevOps. Omit `-u` so your local `main` continues tracking personal GitHub. Only committed files move: `.env`, local certificates, databases and exported image archives must remain untracked. If the company repository already contains commits, import through its approved branch/PR process; do not force-push or use `--mirror`.

The existing `.github/workflows/` files may remain in the repository, but Azure DevOps does not execute them. Keep GitHub's `AZURE_DEPLOY_ENABLED` deployment gate unset or `false` so Azure Pipelines is the only Azure deployer.

## 3. Create the Azure service connection and production environment

In **Project settings → Service connections → New service connection**:

1. Select **Azure Resource Manager**.
2. Use **workload identity federation** and the company-approved application or managed identity.
3. Select the approved subscription/resource group and name the connection exactly `HRProcess-Azure`, matching the YAML's service-connection inputs.
4. Have IT assign the scoped permissions in step 1 to this connection's identity.
5. Authorize this pipeline to use the connection. Do not enable access for unrelated pipelines.

Federation uses short-lived authentication; no Azure client secret or ACR admin password is needed in the YAML. If you cannot create the federated identity, IT can provide the service connection.

In **Pipelines → Environments**, create `hrprocess-production`. Apply the company's existing deployment checks if required. An exclusive lock can serialize deployments; the YAML uses sequential lock behavior. The pipeline uses this exact environment name.

## 4. Create the pipeline variable group

Go to **Pipelines → Library → + Variable group**. Name it exactly:

```text
HRProcess-Azure-Config
```

Add these non-secret values and authorize the pipeline to use the group:

| Variable | Value |
| --- | --- |
| `AZURE_ACR_NAME` | Registry resource name, without `.azurecr.io` |
| `AZURE_ACR_LOGIN_SERVER` | Exact login server returned by ACR, without `https://` |
| `AZURE_RESOURCE_GROUP` | Web App resource group |
| `AZURE_WEBAPP_NAME` | Existing Linux Web App resource name |
| `AZURE_PUBLIC_APP_URL` | Actual public HTTPS origin, e.g. `https://ACTUAL_HOST`; no path or `:7242` |
| `AZURE_DEPLOY_ENABLED` | `false` initially |

Use the actual Azure hostname; newer App Service hostnames can contain generated suffixes. Runtime credentials belong in App Service/Key Vault, not this variable group or Docker build arguments.

## 5. Run the first image build without deploying

In **Pipelines → New pipeline**:

1. Choose **Azure Repos Git** and the company repository.
2. Choose **Existing Azure Pipelines YAML file**.
3. Select branch `main` and path `/azure-pipelines.yml`.
4. Run the pipeline and approve its resource authorizations if requested.

The three stages are **Verify → BuildPush → Deploy**. Verify runs the existing application checks with test Redis/PostgreSQL and a demo browser flow. BuildPush runs only after verification succeeds on branch `main`; feature/PR validation does not publish images. Deploy also requires `AZURE_DEPLOY_ENABLED=true` and any company-configured production checks.

For this first run, keep `AZURE_DEPLOY_ENABLED=false`: verification and image publishing run while deployment stays disabled. BuildPush builds `Dockerfile.azure` for Linux/amd64 and pushes:

```text
YOUR_ACR_LOGIN_SERVER/talentmatch-portal:BUILD_ID
```

The tag is the Azure Pipelines run's `Build.BuildId`; the image also records `Build.SourceVersion` as its revision. Find the tag in **ACR → Repositories → talentmatch-portal**. No portable ZIP, `images.tar`, or local Docker upload is needed for this route.

If Microsoft-hosted agent capacity is unavailable for the organization, IT must enable it or supply an approved self-hosted Linux pool and update the YAML's pool configuration.

## 6. Configure the Linux Web App once

In App Service, configure the existing ACR image and managed-identity image pulls. Keep the image startup command empty: its entrypoint starts all four services.

Set **HTTPS Only**, **Always On**, health path `/healthz`, startup timeout 600 seconds, and **one instance**. This image embeds Redis; do not enable autoscale or run independent production slots with separate Redis instances.

For classic custom-container App Service, set `WEBSITES_PORT=8080`. For sidecar-enabled App Service, configure the main container target port as **8080** instead; `WEBSITES_PORT` does not select its target port.

Use [the application-settings template](../deploy/azure/appsettings.example.json) as the field checklist. Enter actual values in **App Service → Settings → Environment variables**, or use approved Key Vault references. Do not copy your local `.env` blindly. Set these Azure-specific values:

```dotenv
APP_ENV=production
DEMO_MODE=false
FRONTEND_BASE_URL=https://ACTUAL_PUBLIC_HOST
BACKEND_BASE_URL=https://ACTUAL_PUBLIC_HOST
CORS_ALLOWED_ORIGINS=["https://ACTUAL_PUBLIC_HOST"]
LINKEDIN_REDIRECT_URI=https://ACTUAL_PUBLIC_HOST/auth/linkedin/callback
METADATA_BACKEND=postgres
DATABASE_SSLMODE=verify-full
DATABASE_SSLROOTCERT=
D365_CONTRACT_MODE=sqlite
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_PREFIX=talentmatch-production
WEBSITES_PORT=8080
WEBSITES_ENABLE_APP_SERVICE_STORAGE=false
WEBSITES_CONTAINER_START_TIME_LIMIT=600
WEBSITE_WARMUP_PATH=/healthz
WEBSITE_WARMUP_STATUSES=200
```

Keep the working Supabase `DATABASE_URL`, D365 integration settings and three service paths, Azure OpenAI deployment/settings, private Blob settings, LinkedIn credentials, and HR username/password. Use secure App Service settings or Key Vault references for their secrets. `D365_CONTRACT_MODE=sqlite` still selects the lean ERP contract; the metadata engine is PostgreSQL.

For database TLS, a blank `DATABASE_SSLROOTCERT` uses the container's system trust. If Supabase's endpoint needs an additional CA, provide its trusted public CA certificate at a readable **Linux runtime path**, then set `DATABASE_SSLROOTCERT` to that path. A Windows path such as `C:\...` or your local `.local` file does not exist in the image. Use the approved App Service mount/configuration mechanism. The certificate is trust material, not a private key. Complete this before enabling deployment; the production preflight rejects `DATABASE_SSLMODE=require`.

The browser uses the same public host for frontend and API requests; no `VITE_API_BASE_URL` or frontend database credential is required. Azure handles public HTTPS on **443**, then forwards internally to Nginx on **8080**. Do not upload local mkcert certificates to this Azure image.

Supabase already contains your migrated records. Keep the same private Blob account/container to retain resume access. Neither ERP records nor resumes are inside the Docker image.

## 7. Register the callback and enable deployment

After the final Azure hostname/domain and HTTPS are ready, register this exact authorized redirect URL in the LinkedIn developer application:

```text
https://ACTUAL_PUBLIC_HOST/auth/linkedin/callback
```

It must match `LINKEDIN_REDIRECT_URI` in App Service. There is no `:7242` suffix in Azure. Local Docker can keep its separate `https://localhost:7242/auth/linkedin/callback` configuration where permitted by your LinkedIn application setup.

Before cutover, stop the old native/local Docker backend and worker that use the same Supabase dataset. Then:

1. Change `AZURE_DEPLOY_ENABLED` to `true` in `HRProcess-Azure-Config` and save.
2. Run the pipeline on `main` again.
3. Approve `hrprocess-production` deployment if configured.
4. Wait for build, image push, deploy and revision/readiness verification to finish.

Changing a variable group does not start a pipeline automatically. An image push alone does not update the Web App; the deployment stage does that. Later `main` pushes trigger the pipeline automatically.

Open the public application and `/hr` directly. Confirm `/healthz` returns `status: ok` and the deployed Git revision. Then verify LinkedIn returns to the selected job, an application reaches D365, a resume remains accessible to authorized HR, and AI results save to `UBHRMatchEvaluationTable`. The health endpoint checks internal readiness; it does not validate every external credential or workflow.

## 8. Daily GitHub → local → Azure DevOps workflow

While personal GitHub remains the temporary source of changes, after a GitHub update run:

```powershell
cd C:\Users\sritharoon.as\Documents\Projects\UB_HRProcess_Agent
git pull --ff-only origin main
git push company main
```

The Azure DevOps `main` push starts the pipeline. Commit `azure-pipelines.yml` changes through this same route; selecting **Existing YAML** avoids generating a separate company-only pipeline commit.

If company `main` requires PRs, push the corresponding GitHub feature branch to `company` and open an Azure Repos PR instead of bypassing branch protection. Merge/squash commits created by Azure DevOps can make the two `main` branches diverge. Sync those company commits back into personal GitHub through the approved review process before resuming the two-command flow. If a push is rejected or `--ff-only` fails, stop and reconcile the branches; do not force-push.

Once the company repository becomes the sole source, retire this temporary two-repository workflow and make normal company branches/PRs there.

## 9. Logs and rollback

Use **Azure Pipelines → Run → Job logs** for build/deploy failures and **App Service → Log stream** for runtime stage logs. If runtime fails immediately, check resolved Key Vault references, actual public URLs, database TLS settings and container target port before changing application code.

Retain previous verified ACR image tags. For rollback, select a previous verified image in App Service's container configuration and restart; verify its `/healthz` revision. An image rollback does not roll back Supabase, Blob or D365 data. Disable automatic deployment temporarily while investigating.

For more runtime details, use [the Azure App Service guide](azure-app-service.md), sections 3, 5 and 10–11. Its GitHub Actions setup sections describe the alternate GitHub deployment route; this guide replaces those sections with Azure Pipelines.
