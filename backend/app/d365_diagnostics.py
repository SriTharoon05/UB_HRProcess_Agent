"""Bounded, value-free diagnostics for untrusted F&O error responses.

Provider text is never returned verbatim. Only messages emitted by our shipped
UBHR service are reconstructed, using known tables/fields and numeric lengths.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx

MAX_ERROR_BYTES = 65536
MAX_MESSAGE_CHARS = 4096

_COMPANY_MESSAGE = "Company must match the integration user's configured current company."
_FIXED_MESSAGES = {
    _COMPANY_MESSAGE: ("company_mismatch", "Match D365_COMPANY to the F&O integration user's current legal entity."),
    "The _request parameter is required.": ("request_wrapper_missing", "Check D365_PARAMETER_NAME and the deployed contract; the default wrapper is _request."),
    "ApplicationId is already assigned to a different requirement or identity.": ("application_identity_conflict", "Check the frozen application identifier and requirement; retry only the original submission."),
    "The requirement is not accepting applications.": ("requirement_closed", "Check RequirementStatus, UTC OpenDate/CloseDate and legal entity in F&O."),
    "The candidate identity key does not match its stored identity.": ("candidate_identity_conflict", "Check existing candidate identity mapping and unique IdentityKey index."),
    "The candidate record could not be validated. Check the existing table's business defaults.": ("candidate_validation_failed", "Inspect UBCandidateTable.validateWrite(), mandatory fields and business defaults in F&O."),
    "The application record could not be validated. Check the existing table's business defaults.": ("application_validation_failed", "Inspect UBJobApplicationTable.validateWrite(), mandatory fields and business defaults in F&O."),
    "The evaluation record could not be validated. Check the existing table's business defaults.": ("evaluation_validation_failed", "Inspect UBHRMatchEvaluationTable.validateWrite(), mandatory fields and business defaults in F&O."),
    "The completed application record could not be validated.": ("completed_application_validation_failed", "Inspect UBJobApplicationTable.validateWrite() and AIStatus/OverallScore field mappings in F&O."),
    "Concurrent submission could not be resolved. Retry with the same ApplicationId.": ("submission_concurrency", "Retry the original submission with the same frozen ApplicationId."),
    "Concurrent submission update could not be resolved. Retry with the same ApplicationId.": ("submission_concurrency", "Retry the original submission with the same frozen ApplicationId."),
    "Concurrent evaluation could not be resolved. Retry with the same EvaluationId.": ("evaluation_concurrency", "Retry the saved evaluation with the same stable EvaluationId."),
    "Concurrent evaluation update could not be resolved. Retry with the same EvaluationId.": ("evaluation_concurrency", "Retry the saved evaluation with the same stable EvaluationId."),
    "Score must be between 0 and 100.": ("evaluation_score_invalid", "Check the validated evaluation Score range and deployed contract type."),
    "ApplicationId and RequirementId must identify the same existing application.": ("evaluation_application_missing", "Check that application creation was acknowledged in the same legal entity before evaluation."),
    "EvaluationId is already assigned to a different application or requirement.": ("evaluation_identity_conflict", "Check the frozen ApplicationId/RequirementId and stable EvaluationId mapping."),
    "Use the same stable EvaluationId when updating an application's current evaluation.": ("evaluation_identity_conflict", "Retry with the existing stable EvaluationId for this application."),
    "The existing evaluation has an inconsistent requirement reference.": ("evaluation_requirement_conflict", "Check the existing evaluation's application/requirement relationships in F&O."),
    "MeetsMinimumCriteria must be a NoYes enum or integer field.": ("boolean_mapping_invalid", "Use an existing NoYes enum or integer field for MeetsMinimumCriteria."),
    "MeetsMinimumCriteria must use the existing No/Yes enum symbols.": ("boolean_mapping_invalid", "Check the existing enum has the No and Yes symbols."),
    "MeetsMinimumCriteria integer value must be 0 or 1.": ("boolean_mapping_invalid", "Check existing MeetsMinimumCriteria integer data is 0 or 1."),
    "Email must be a contact email address.": ("contact_email_invalid", "Check the submitted contact email format; provider identity is not a contact email."),
    "Email must contain only a contact email address.": ("contact_email_invalid", "Submit a plain contact email without a display name."),
    "LinkedInProfileUrl must be a valid HTTPS LinkedIn profile URL.": ("linkedin_url_invalid", "Check the optional profile URL uses HTTPS and a linkedin.com hostname."),
}

# Values here are AOT metadata from the user's tables, never request values.
_TABLE_FIELDS = {
    "UBJobRequirementTable": {"RequirementId", "RequirementStatus", "WorkMode", "EmploymentType"},
    "UBCandidateTable": {"CandidateId", "IdentityKey", "LinkedInIssuer", "LinkedInSub", "FirstName", "LastName", "Email", "Phone", "LinkedInProfileUrl"},
    "UBJobApplicationTable": {"ApplicationId", "CandidateId", "RequirementId", "ApplicationStatus", "AIStatus"},
    "UBHRMatchEvaluationTable": {"EvaluationId", "ApplicationId", "RequirementId", "MatchLabel", "Summary", "MatchedSkillsJson", "MissingSkillsJson", "EvidenceJson", "MeetsMinimumCriteria"},
}
_EXCEPTION_TYPES = {
    "ErrorException", "Exception", "XppException", "ClrErrorException", "UpdateConflictException",
    "DuplicateKeyException", "DuplicateKeyExceptionNotRecovered", "UpdateConflictNotRecovered",
    "System.Exception", "System.InvalidOperationException", "System.ArgumentException",
    "System.NullReferenceException", "System.Data.SqlClient.SqlException",
    "Microsoft.Data.SqlClient.SqlException", "Microsoft.Dynamics.Ax.Xpp.ErrorException",
    "Microsoft.Dynamics.Ax.Xpp.XppException", "Microsoft.Dynamics.Ax.Xpp.UpdateConflictException",
    "Microsoft.Dynamics.Ax.Xpp.DuplicateKeyException", "System.UnauthorizedAccessException",
    "Microsoft.Dynamics.Ax.Xpp.InfoException", "Newtonsoft.Json.JsonSerializationException",
}


def _uuid(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _known_message(message: str) -> dict[str, Any] | None:
    # The F&O runtime wraps custom-service errors in an operation failure prefix.
    # Reconstruct the recognized fragment, discarding ALL surrounding text.
    for canonical, (code, hint) in _FIXED_MESSAGES.items():
        if canonical in message:
            return {"issue_code": code, "hint": hint, "provider_message": canonical}
    for table, fields in _TABLE_FIELDS.items():
        for field in fields:
            prefix = f"{table}.{field}"
            length = re.search(re.escape(prefix) + r" is missing or exceeds its existing field length \(([0-9]{1,7})\)\.", message)
            if length:
                maximum = int(length.group(1))
                return {"issue_code": "field_length_or_missing", "table": table, "field": field,
                        "max_length": maximum, "provider_message": f"{prefix} is missing or exceeds its existing field length ({maximum}).",
                        "hint": "Inspect this existing field's EDT/StringSize and required value; IDs need 40 characters and IdentityKey needs 64."}
            for suffix, code, hint in (
                ("must be a string field for this service mapping.", "field_type_invalid", "Check the existing field is a string EDT for the deployed UBHR mapping."),
                ("contains an unknown enum value.", "enum_value_invalid", "Check existing enum data and the deployed status configuration symbols."),
                ("must be an enum or string field for the status mapping.", "status_field_type_invalid", "Check the existing status field type is Enum or String."),
            ):
                canonical = f"{prefix} {suffix}"
                if canonical in message:
                    return {"issue_code": code, "table": table, "field": field,
                            "provider_message": canonical, "hint": hint}
    for field, prefix in (("ApplicationId", "APP-"), ("EvaluationId", "EVA-")):
        canonical = f"{field} must contain the stable {prefix} identifier supplied by the backend."
        if canonical in message:
            return {"issue_code": "external_id_invalid", "field": field, "provider_message": canonical,
                    "hint": "Use the stable backend-generated identifier; check DTO field length and request mapping."}
    for field in ("MatchedSkillsJson", "MissingSkillsJson", "EvidenceJson"):
        for suffix, code in (("exceeds the supported JSON payload size.", "evaluation_json_too_large"),
                             ("must contain a valid JSON array; use [] for an empty collection.", "evaluation_json_invalid")):
            canonical = f"{field} {suffix}"
            if canonical in message:
                return {"issue_code": code, "field": field, "provider_message": canonical,
                        "hint": "Check evaluation JSON array serialization and the existing memo field mapping."}
    enum_error = re.search(r"Enum [A-Za-z_][A-Za-z0-9_]{0,63} has no symbol '(Open|Pending|Completed|No|Yes)'\. Set the service configuration method to your actual existing enum symbol\.", message)
    if enum_error:
        # Enum names are user-defined; suppress them rather than printing a
        # provider-controlled identifier that could be a credential or subject.
        symbol = enum_error.group(1)
        return {"issue_code": "enum_symbol_missing", "enum_symbol": symbol,
                "provider_message": f"The existing enum has no symbol '{symbol}'.",
                "hint": "Match UBHRPortalService status configuration methods to actual AOT enum symbols; AIStatus defaults to Pending/Completed."}
    return None


def d365_error_diagnostics(response: httpx.Response) -> dict[str, Any]:
    """Return scalar safe metadata; this must never throw or expose raw bodies."""
    diagnostics: dict[str, Any] = {"issue_code": "d365_unclassified",
                                  "hint": "Inspect the F&O exception/Infolog using activity_id; unknown provider text is suppressed."}
    for header in ("x-ms-diagnostics-activity-id", "x-ms-activity-id", "activityid", "x-correlation-id", "request-id"):
        value = _uuid(response.headers.get(header))
        if value:
            diagnostics["activity_id"] = value
            break
    if len(response.content) > MAX_ERROR_BYTES:
        diagnostics["response_kind"] = "oversized"
        return diagnostics
    try:
        body = json.loads(response.content)
        if isinstance(body, str) and len(body) <= MAX_MESSAGE_CHARS:
            body = json.loads(body)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        diagnostics["response_kind"] = "non_json"
        return diagnostics
    diagnostics["response_kind"] = "json"
    stack = [(body, 0)]
    visited = 0
    while stack and visited < 64:
        node, depth = stack.pop()
        visited += 1
        if depth > 5:
            continue
        if isinstance(node, dict):
            for key, value in list(node.items())[:32]:
                if not isinstance(key, str):
                    continue
                key = key.lower()
                if key in {"activityid", "activity_id", "correlationid", "correlation_id"}:
                    activity = _uuid(value)
                    if activity:
                        diagnostics.setdefault("activity_id", activity)
                elif key in {"exceptiontype", "exception_type"} and isinstance(value, str):
                    if value in _EXCEPTION_TYPES:
                        diagnostics.setdefault("exception_type", value)
                elif key == "message" and isinstance(value, str) and len(value) <= MAX_MESSAGE_CHARS:
                    known = _known_message(value)
                    if known and diagnostics["issue_code"] == "d365_unclassified":
                        diagnostics.update(known)
                elif key in {"error", "innererror", "innerexception", "details", "infolog"} and isinstance(value, (dict, list)):
                    stack.append((value, depth + 1))
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node[:16] if isinstance(item, (dict, list)))
    return diagnostics
