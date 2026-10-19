# ubticareers: Azure DevOps Server CI/CD

The root [azure-pipelines.yml](../azure-pipelines.yml) automates company Azure Repos Git -> Azure Pipelines -> ACR -> the existing Linux App Service. Adding it does not create cloud resources, change the live application, or migrate databases. The personal GitHub repository remains a temporary development mirror; the company Azure Repos pipeline performs deployments.

The pipeline is prepared for a modern Azure DevOps Server installation with multi-stage YAML and deployment environments. Confirm the server version and available AzureCLI@2 task if your installation is older. Use the compatible agent download supplied by your own server.

## Existing resources

| Item | Value |
| --- | --- |
| Project URL | https://devops.ubtiinc.com/Solutions/HR-Process |
| Agent registration collection URL | https://devops.ubtiinc.com/Solutions |
| Proposed Git repository | ubticareers |
| Subscription ID | 60730d88-4cfc-4e6d-8c19-3e9591bc14bd |
| Subscription name | MSSponsor UIAP - Internal3 |
| Resource group | ubti-hrprocess-rg |
| ACR name | hrprocess |
| ACR login server | hrprocess-h9fqfaa0d8h0dca3.azurecr.io |
| ACR repository | ubticareers |
| Existing Web App | ubtihrprocess |
| Existing main sitecontainer | main |
| Container port | 8080 |
| Public origin | https://ubtihrprocess-egg3f7awbsbjdjd5.centralindia-01.azurewebsites.net |

The current Web App is sidecar-enabled. This YAML updates its existing main container using `az webapp sitecontainers update`; it does not use classic `az webapp config container set` or convert the Web App to another mode.

## 1. Use the imported company Git repository

The GitHub repository has already been imported into the HR-Process Azure DevOps project. Use that existing repository; do not import it again or replace its history. Confirm the main branch contains frontend, backend, Dockerfile.azure and azure-pipelines.yml.

Select Repos -> Files -> Clone and copy the exact HTTPS clone URL. If the repository is named ubticareers, the expected shape is `https://devops.ubtiinc.com/Solutions/HR-Process/_git/ubticareers`; use the actual URL displayed by the server, since the imported repository may have another name.

GitHub import copies the repository once. It does not continuously synchronize future GitHub commits and does not create an agent, Azure service connection or pipeline. Follow section 6 to push these CI/CD updates into the existing company repository.

## 2. Arrange an online Linux build agent

This company URL appears to be Azure DevOps Server. Microsoft-hosted agents such as `ubuntu-latest` are not available on on-premises Azure DevOps Server. Open Project settings -> Agent pools and prefer an existing approved online Linux agent. Replace the YAML pool name `ubticareers-linux` if using another existing pool.

If there is no Linux agent, a pool administrator/IT must create or authorize the pool and register an agent on an approved Linux x64 machine. ACR and App Service do not provide this agent. Do not register it inside the production application container.

The agent needs:

- A server-compatible Azure Pipelines agent, configured to run as a service.
- Git, Bash, curl, Python 3.12 (`python3.12` on PATH), Node.js 22 with npm, and uv 0.12.23.
- Docker Engine with BuildKit/buildx and daemon access for the agent service account.
- Current Azure CLI supporting `az webapp sitecontainers update`.
- Playwright Chromium system libraries. The pipeline downloads the browser as the agent user; install the OS libraries once using the installed Playwright CLI and an approved administrator account.
- Network access to the company DevOps collection, Microsoft Entra/Azure management, ACR, package registries, container base-image registries, Playwright browser downloads, and the public Web App health endpoint.
- Available local ports 8000 and 5173 for the fictional browser test. PostgreSQL and Redis test-container host ports are allocated dynamically.

Use Project settings -> Agent pools -> selected pool -> New agent -> Linux. Follow that server's download/extraction instructions. In the agent directory, run `./config.sh` and enter `https://devops.ubtiinc.com/Solutions` as the server/collection URL, the approved authentication method, and the selected pool. Enter a registration PAT only at the secure prompt, if your company uses PAT registration; never add it to YAML or Git. Registration requires the relevant pool-management permission.

For an approved Linux service setup, the usual commands after registration are `sudo ./svc.sh install` and `sudo ./svc.sh start`. Confirm the agent appears Online. Restart the agent service after installing new tools so it inherits the updated PATH. Use one agent per machine initially to avoid browser-test port conflicts.

After the backend dependencies are installed, IT can install browser OS libraries once with the equivalent of `sudo /ABSOLUTE/CHECKOUT/backend/.venv/bin/python -m playwright install-deps chromium`. This is an agent preparation step, not a command to run inside the live application.

## 3. Create or reuse the Azure Resource Manager service connection

Open Project settings -> Service connections -> New service connection -> Azure Resource Manager. Name it `ubticareers-azure`, or substitute an existing approved connection name at both AzureCLI@2 inputs in the YAML.

For Azure DevOps Server, Microsoft's documented method is Service principal (manual), using a company-approved deployment application/service principal and its credential. Reuse an existing approved connection if available. Workload identity federation guidance for Azure DevOps Services should not be assumed to apply to this server. If the installed server supports a company-approved secretless method, IT can supply that connection instead.

Set Azure Cloud and the subscription ID/name listed above. Select the resource group if offered, and enter the deployment identity's client/application ID, tenant ID, and approved credential. IT must supply or configure these because the user was not granted Entra app-registration administration. A D365 application credential is not automatically an Azure deployment identity. Keep a deployment secret only in the service connection, not YAML, variable groups, Docker build arguments, or the application .env.

The connection's identity needs these scoped roles:

| Resource | Role |
| --- | --- |
| ACR hrprocess | Reader plus AcrPush |
| App Service ubtihrprocess | Website Contributor |

These ACR roles assume classic registry RBAC; ABAC-enabled registries require the corresponding repository permissions. The identity does not need subscription Owner or resource-group Contributor. Selecting a subscription in the service-connection form does not itself grant subscription-wide access. An optional subscription Reader assignment may be required by the company's connection-discovery/verification process; have IT use its supported method.

Verify and save. Authorize only this pipeline to use the connection. The Web App's image-pull managed identity is separate and keeps its existing AcrPull permission; granting AcrPush to your personal account does not grant it to the pipeline.

## 4. Create the variable group

Go to Pipelines -> Library -> + Variable group. Name it `ubticareers-azure-config` and enter:

| Variable | Value |
| --- | --- |
| AZURE_ACR_NAME | hrprocess |
| AZURE_ACR_LOGIN_SERVER | hrprocess-h9fqfaa0d8h0dca3.azurecr.io |
| AZURE_RESOURCE_GROUP | ubti-hrprocess-rg |
| AZURE_WEBAPP_NAME | ubtihrprocess |
| AZURE_PUBLIC_APP_URL | https://ubtihrprocess-egg3f7awbsbjdjd5.centralindia-01.azurewebsites.net |
| AZURE_DEPLOY_ENABLED | false |

Authorize this pipeline to use the group. These are resource settings, not runtime secrets. Keep the working database, D365, LinkedIn, HR, Blob and AI credentials in App Service settings.

## 5. Create the deployment environment

Go to Pipelines -> Environments -> New environment. Name it `ubticareers-production` and choose no additional resource (None). The AzureCLI task deploys to the already-existing Web App; this environment tracks deployments and any checks.

Authorize the pipeline. Configure any required company approval and exclusive-lock checks if available and required by policy. Environments do not themselves create a Web App, change permissions, or deploy a container. If this menu/YAML feature is unavailable, confirm the Azure DevOps Server version before selecting the YAML.

## 6. Pull these updates and push them to the existing company repository

The root azure-pipelines.yml now uses the ubticareers image repository, a self-hosted Linux pool, the company service connection, and the existing main sitecontainer. Pull the latest personal GitHub commit locally before updating Azure Repos. The older pipeline from the initial import used a hosted agent and classic container deployment.

Review local changes and the remote URLs. Keep .env, private keys, SQLite files, uploaded resumes and private connection settings untracked. The public Supabase CA remains in App Service persistent storage; CI's local PostgreSQL test container does not require it.

From PowerShell:

```powershell
cd C:\Users\sritharoon.as\Documents\Projects\UB_HRProcess_Agent
git status --short
git switch main
git pull --ff-only origin main
git remote -v
git remote add company "PASTE_THE_EXACT_HTTPS_CLONE_URL_FROM_AZURE_DEVOPS"
git fetch company
git push company main
```

If company already exists, inspect its URL instead of adding it again. Use `git remote set-url company "EXACT_CLONE_URL"` only if the configured URL is incorrect. The company repository was imported from GitHub, so these updates can be pushed normally when the histories remain aligned. If the company repository has additional commits or main is protected, synchronize through an approved branch/PR instead of force-pushing. If a fast-forward pull or push is rejected, reconcile the histories before proceeding.

GitHub remains the temporary development mirror. Keep company-created pipeline edits and merge commits synchronized back to it while using this arrangement. Once Azure Repos becomes canonical, use the company's normal branch/PR workflow.

## 7. Create the pipeline and run the first build without deployment

Go to Pipelines -> New pipeline -> Azure Repos Git -> your existing imported repository -> Existing Azure Pipelines YAML file -> branch main -> `/azure-pipelines.yml`. Name the pipeline `ubticareers-ci-cd`. Authorize the pool, variable group, service connection, and deployment environment when prompted, using the relevant administrator if permission is missing.

Keep AZURE_DEPLOY_ENABLED=false. Run on main.

The stages are:

1. Verify: locked dependencies, Python/frontend checks, ERP bundle validation, tests against local Redis/PostgreSQL containers, frontend build, and the existing fictional browser smoke workflow. No production AI, D365, Supabase, or LinkedIn credentials are required for these tests.
2. BuildPush: build Dockerfile.azure, embed the commit revision, push `hrprocess-h9fqfaa0d8h0dca3.azurecr.io/ubticareers:BUILD_ID`, and resolve the immutable image digest.
3. Deploy: skipped while deployment is disabled.

Confirm ACR -> Repositories -> ubticareers contains the new numeric tag. The running phase1-v1 image is not changed by this first build. A pipeline run must actually pass before its configuration can be considered verified.

## 8. Enable deployment

Keep all working runtime settings unchanged, including:

```dotenv
WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
DATABASE_SSLMODE=verify-full
DATABASE_SSLROOTCERT=/home/certs/supabase-ca.crt
```

Preserve the uploaded `/home/certs/supabase-ca.crt` and the existing India Supabase DATABASE_URL. Do not repeat the migration. This YAML never uploads app settings, reads secrets, or replaces /home. The existing main container's authentication is preserved; the image and target port are updated and its blank startup command is retained.

Once the first run passes, set AZURE_DEPLOY_ENABLED=true in the variable group. Save and run the pipeline again on main. A variable-group edit does not trigger a run by itself.

The deployment updates the existing main sitecontainer to the exact published digest, restarts the Web App, and polls /healthz until both `status=ok` and `revision=Build.SourceVersion`. One App Service instance is retained because Redis is embedded. Deployments involve a brief restart and sessions may need a fresh login.

Open the public site and /hr after deployment. A passing readiness check verifies internal startup, not the external business integrations. LinkedIn callback registration remains separate, and the GPT-5.4-mini client compatibility update has not been implemented by this CI/CD configuration.

## 9. Configure PR validation and choose the daily source workflow

After the first run works, go to Repos -> Branches -> main -> Branch policies. Configure required reviewers and Build validation using this pipeline. Azure Repos PR validation is a branch-policy setting; `pr: none` in YAML avoids assuming GitHub PR triggers. A PR validation build runs verification without publishing or deploying because its source branch is not refs/heads/main.

When direct main pushes are permitted during the temporary mirror phase, updates can follow:

```powershell
git switch main
git pull --ff-only origin main
git push company main
```

After main is protected, use company feature branches and PRs instead of bypassing the policy. Prefer making Azure Repos the canonical repository at that point. If personal GitHub must remain a mirror, include company-created merge/squash commits when syncing back; do not use the two-command fast-forward workflow blindly after histories diverge and do not force-push. Azure DevOps runs the YAML; the .github workflow directory does not run on Azure Repos. Keep GitHub deployment disabled so there is only one deployment pipeline.

## 10. Troubleshooting and rollback

| Symptom | Next check |
| --- | --- |
| Waiting for agent | Pool name, Online agent, authorization and parallel-job capacity on the company server |
| YAML/task/environment unsupported | Installed Azure DevOps Server version and available task versions |
| Service connection not found/authorized | Exact ubticareers-azure name and pipeline-use permission |
| npm/uv/browser downloads fail | Agent network/trust configuration and disk space; preserve TLS verification |
| Browser launch reports missing libraries | Install Playwright OS dependencies on the agent, then rerun |
| ACR push denied | Pipeline service connection identity's AcrPush/repository-writer permission |
| Container update denied | Website Contributor on ubtihrprocess for the pipeline identity |
| App Service image pull denied | App Service managed identity's separate AcrPull/repository-reader permission and main-container authentication |
| Database TLS failure | Persistent CA path, uploaded file and verify-full settings; leave persistent storage enabled |
| Readiness returns the previous revision | Wait for image pull/startup; inspect the main container image/digest and fresh runtime logs |
| Readiness succeeds, AI fails | Check the application model-client integration separately; CI does not add the pending GPT-5.4-mini update |

Retain known-good image tags/digests. For rollback, first set AZURE_DEPLOY_ENABLED=false to stop subsequent automatic deployments, then select the previous verified image on App Service -> Deployment Center -> Containers -> main, Apply, and restart. Already-running deployments need to be stopped separately if applicable. Verify /healthz again. An image rollback does not revert Supabase, Blob or D365 data.

## Official references

- Azure DevOps Server and hosted-agent limitation: https://learn.microsoft.com/en-us/azure/devops/pipelines/agents/hosted
- Linux self-hosted agent: https://learn.microsoft.com/en-us/azure/devops/pipelines/agents/linux-agent
- Azure Resource Manager service connections (select your Server version): https://learn.microsoft.com/en-us/azure/devops/pipelines/library/connect-to-azure
- Sidecar App Service configuration: https://learn.microsoft.com/en-us/azure/app-service/configure-sidecar
- Sitecontainer CLI commands: https://learn.microsoft.com/en-us/cli/azure/webapp/sitecontainers

The agent, service-connection and sidecar guidance was checked against Microsoft's official documentation/source. The pipeline YAML and shell/Python syntax are checked separately; it has not been executed on the company's server or deployed with company credentials.
