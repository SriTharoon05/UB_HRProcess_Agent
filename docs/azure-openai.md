# Azure OpenAI evidence evaluation

The connected evaluation service uses the Azure OpenAI Python SDK and the configured deployment. Its score is the model's contextual estimate of how thoroughly the **complete resume** documents the **complete job's** requirements. Python validates the score as an integer from 0 to 100 and preserves it. There are no category weights, keyword formulas, accepted/rejected thresholds, or automated hiring decisions.

## Configuration

```dotenv
AZURE_OPENAI_ENDPOINT=https://voiceagentdemo-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_API_VERSION=2025-03-01-preview
AZURE_OPENAI_PROMPT_VERSION=v1
AZURE_OPENAI_MAX_RESUME_CHARS=100000
```

The supplied deployment/API-version combination is configurable and has not been validated against the live resource in this credential-free build. Confirm that your deployed model and Azure API version support structured outputs and the SDK's `beta.chat.completions.parse` interface. A deployment is an Azure deployment name, which may differ from the underlying model name. If the deployment returns an unsupported-feature error, choose a supported Azure deployment/API version; the application does not downgrade to unvalidated free-form output.

The prompt lives at `backend/app/services/prompts/evaluation_v1.txt`. `AZURE_OPENAI_PROMPT_VERSION` must reference an installed `vN` prompt file. Changing the environment variable alone does not create a prompt. Commit and review new prompt versions, and retain provenance with the evaluation.

## Input and output validation

The worker extracts all readable PDF pages or DOCX paragraphs, tables, text boxes, content controls, hyperlinks, headers, and footers. It supplies job description, responsibilities, required/preferred skills, qualifications, certifications, and any optional structured criteria in the typed job context. Work and project descriptions count even when a technology is absent from the dedicated Skills section.

The prompt distinguishes a technology mention from demonstrated personal implementation, prohibits invented evidence and protected-characteristic reasoning, and treats document content as untrusted data. Commands/instructions embedded in a resume or JD are not executed. The model uses a low-variability temperature of `0.1`.

Structured Pydantic output requires:

- An integer `score` between 0 and 100, the evidence `match_label`, and `meets_minimum_criteria`.
- Non-empty `score_justification` and `summary`.
- Matched and partially supported requirement objects with requirement, section, project name when applicable, exact quote, reasoning, and evidence strength.
- Not-evidenced requirements with an uncertainty-aware explanation.
- Supporting resume evidence and High/Medium/Low confidence.

The backend verifies evidence excerpts as exact substrings of both the submitted model text and the original extracted text. A non-empty project name must appear in the supplied resume. A positive score without any supporting evidence is rejected. A syntactically valid quote does not prove the reasoning or resume claims are true: HR must inspect context and verify relevant assertions.

The service does not silently truncate the resume or JD. An extracted resume exceeding `AZURE_OPENAI_MAX_RESUME_CHARS` fails explicitly before the model call; increase that guard only within the actual deployment's supported context. An unreadable/scanned document fails extraction with an OCR explanation. A model refusal, invalid schema, unsupported quote, or context-window/deployment incompatibility becomes a visible evaluation failure rather than an invented score.

## Identity minimization

The service removes obvious email addresses, phone numbers, LinkedIn URLs, leading name lines when recognized, and explicitly labeled personal fields before model submission. This is **best-effort minimization**, not guaranteed anonymization; identifiers in narrative can remain. Configure the Azure resource's approved region/data-processing controls and review the privacy notice for real candidate documents.

## Worker and persistence

The candidate receives a submission confirmation after D365 confirms an application ID and work is queued. A separate Redis-backed worker processes the document, calls Azure OpenAI, validates the result, and sends it to `saveCandidateEvaluation`. Transient network/throttling/service failures use bounded retries with backoff; deterministic invalid output is reported as failed instead of assigning a fallback score.

The adapter serializes requirement/evidence collections into the proposed X++ memo JSON strings and attaches deployment/prompt/rubric provenance. A missing save endpoint is a configuration blocker and does not count as a persisted evaluation. Retrying persistence requires the D365 service to upsert one evaluation per application. See [D365 endpoints](d365-endpoints.md).

Demo mode selects a separate labeled evaluation fixture and does not invoke this production AI service. Sample values shown in documentation/demo screens are never production fallback scores.

## Live verification

With authorized credentials, test a readable synthetic resume against a complete job, inspect structured output and quotes, verify D365 persistence/acknowledgement, and check HR detail rendering. Also test unreadable documents, unsupported context size, missing Azure configuration, throttling, and missing D365 save operation. Do not use live candidate records to validate a test environment without an appropriate data-processing setup.
