# Terminal logs and debugging

The API and evaluation worker write stage logs to their terminals. Each major operation records when it starts, when it completes, or when it fails, together with its duration. This lets you identify the failing stage without printing candidate details or integration credentials.

## Enable and capture logs

After the updated code is pushed, pull it from PowerShell in your repository folder:

```powershell
git pull --ff-only origin main
cd backend
uv sync --frozen
```

`LOG_LEVEL=INFO` is the default. It includes normal stage progress and failures. Set `LOG_LEVEL=DEBUG` in `backend/.env` for additional diagnostic events, then restart both API and worker:

```dotenv
LOG_LEVEL=DEBUG
```

Debug level does not enable raw provider responses, tokens, request bodies, candidate contact information, resumes, or AI prompts. Return to `INFO` after troubleshooting.

DEBUG includes known D365 contract field names, value types and string lengths. For example, `field="ApplicationId" value_type="str" value_length=40` helps compare the submitted shape against an existing F&O field size. Actual field values stay excluded.

For Windows, open PowerShell in the `backend` folder. Create the ignored output directory:

```powershell
New-Item -ItemType Directory -Force .local | Out-Null
```

Start the existing HTTPS API and capture both stdout and stderr while keeping the output visible:

```powershell
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 7242 --ssl-certfile .certs\localhost.pem --ssl-keyfile .certs\localhost-key.pem 2>&1 |
    Tee-Object -FilePath .local\api-debug.log
```

In a second PowerShell window, also in the same `backend` folder, start and capture the worker:

```powershell
uv run --frozen python -m app.worker 2>&1 |
    Tee-Object -FilePath .local\worker-debug.log
```

Keep Redis running and use the same environment and metadata backend/connection in both processes. SQLite processes must resolve the same durable file; PostgreSQL processes must use the same database. A successful API submission cannot progress through connected AI review without the worker. The PowerShell pipeline is for displaying/capturing logs; use the process output to diagnose startup failures rather than treating the pipeline's success as proof that the server started.

On an existing deployment, inspect the API and worker service logs separately. For the connected Compose arrangement:

```bash
docker compose logs --follow api worker
```

## Read a processing trace

Stage events contain these fields when they apply:

| Field | Meaning |
| --- | --- |
| `stage` | The operation being performed, such as submission, storage, D365, queueing, or evaluation |
| `outcome` | Stage progress (`start`, `completed`, `failed`) or a specific event such as `received`, `queued`, `skipped`, or `reused` |
| `elapsed_ms` | Duration of a completed or failed stage |
| `request_id` | The UUID identifying a browser/API request; returned in the `X-Request-ID` response header |
| `application_id` | The stable application ID linking submission and background evaluation |
| `correlation_id` | The UUID identifying one outgoing D365 call; also included in the portal's D365 failure reference |
| `issue_code`, `hint` | An identified provider/configuration problem and a suggested check |
| `provider_message` | A recognized, safe D365 validation message; never an arbitrary raw response body |
| `activity_id` | A D365 activity ID, when the response supplies a valid one |

An illustrative trace has this structure; the exact stage names depend on the operation:

```text
stage=application.submit outcome=start request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
stage=d365.http outcome=failed request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" application_id="APP-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" operation="submit_application" status_code=500 correlation_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc" issue_code="company_mismatch"
stage=application.submit outcome=failed request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" elapsed_ms=683
```

Start with the most specific failed stage: an outer application/request failure can be the result of an inner storage or D365 failure. A start event without a later completion or failure means the operation is still pending or its process stopped before reporting an outcome. Check both elapsed time and service health.

The API request ID ties together work done while handling that request. The stable application ID connects it to the separate worker process, retries, and the saved evaluation. Each outgoing D365 operation has its own correlation ID; an automatic authentication-refresh retry retains that ID and changes the `attempt` field.

In PowerShell, find the reference shown in the portal or a known application ID:

```powershell
Select-String -Path .local\api-debug.log,.local\worker-debug.log -SimpleMatch "5457f25f-092c-4df4-ad28-8c7922e8338e"
```

Replace the example with the actual ID. To narrow the output to failures:

```powershell
Select-String -Path .local\api-debug.log,.local\worker-debug.log -Pattern 'outcome=failed'
```

## Follow the application stages

| Stage area | What its logs help establish |
| --- | --- |
| Startup | API/worker startup, configuration mode, SQLite initialization, and Redis readiness |
| Authentication | Login redirect, callback validation, profile processing, and session creation |
| Job reads | D365 token acquisition, request, safe HTTP status, response parsing, and job mapping |
| Submission | `application.submit`, `application.validate`, and `job.lookup` identify candidate authorization, job availability, upload validation, document storage, and frozen SQLite submission intent |
| D365 application write | Sending the existing-table contract, provider acknowledgement, and acknowledgement persistence |
| Queue | Evaluation scheduling, duplicate/recovery handling, and enqueue acknowledgement |
| Worker | Job start, retained-state loading, document retrieval, checksum verification, and text extraction |
| AI review | Model request, structured response validation, evidence checks, and durable evaluation caching |
| D365 evaluation write | Core-result save, provider acknowledgement, and final local completion |
| Recovery | Retained submission reconciliation and bounded evaluation retries |

Some operations skip stages deliberately: a repeated acknowledged submission can reuse its original result, and a persistence retry can reuse the already validated AI evaluation. Demo mode does not call the connected D365/Azure services.

## Diagnose a D365 HTTP 500

An event for `submit_application` with HTTP 500 means the upstream F&O service failed. FastAPI reports an upstream integration failure as HTTP 502 to the browser. It does not establish which F&O validation failed or whether a response was lost after a commit.

The diagnostic parser recognizes the source pack's safe validation errors, including:

- The request company differs from the integration user's configured current company.
- A known table field is missing, has an incompatible type, or exceeds its existing string length.
- An existing status enum lacks the configured symbol, such as `Pending` or `Completed`.
- Candidate/application/evaluation table validation rejects existing business defaults.
- A requirement no longer accepts applications or stable IDs do not match the existing record.

Recognized failures include an `issue_code`, a canonical `provider_message`, and a `hint`. Field names and configured length limits can identify the AOT property to check without displaying the submitted value. Check these diagnostics before changing the service or table.

If the provider message is unknown, malformed, or contains arbitrary text, the terminal does not dump it. The HTTP status, operation, correlation ID, and validated activity ID still identify the attempt. Obtain the original exception from the F&O debugger or environment monitoring logs and inspect it in the authorized F&O environment. Do not disable TLS, remove validation, or change table constraints solely because the HTTP status is 500.

For a retained failed evaluation, repair the identified configuration/service problem, restart with the corrected environment, then follow the recovery instructions in [deployment](deployment.md#redis-durability-and-recovery). Do not create another application just to retry an evaluation.

## Logging boundaries

Application logs omit OAuth codes/state query values, cookies, authorization headers, secrets, raw request/response bodies, resume text, AI prompts/results, candidate names/contact details, and storage object references. The Uvicorn access-log filter removes query strings; ARQ job logging avoids raw job arguments and result dumps. Unexpected application exceptions retain safe code locations and the exception type rather than the arbitrary exception value. The application's DEBUG setting does not enable verbose HTTP SDK wire logging.

Request, application, correlation, and activity IDs remain operational identifiers. Review the relevant trace before sharing it, restrict log-file access, and apply your deployment's log retention policy. `.local` and `*.log` files are ignored by Git.

## Portable Docker logs

The source-free runtime bundle uses root `.env`; run its start wrapper after editing settings so containers are recreated. Open Docker Desktop service logs or run `docker compose logs --follow api worker`. The visible portal/health URL is `https://localhost:7242` (`/api/health`). A database/PostgreSQL connection failure is separate from the LLM and ERP stages. Do not print `DATABASE_URL`, `.env` or container environment dumps while collecting logs.
