"""Check source metadata and exercise every example through the actual D365 adapter.

Run from backend: uv run --frozen python ../d365/validate_bundle.py
This is a contract check, not an X++ compiler or a live F&O deployment test.
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

from app.models import Evaluation, Job, LinkedInProfile, User  # noqa: E402
from app.services.d365 import (  # noqa: E402
    MEMO_FIELDS,
    PATHS,
    REQUEST_FIELDS,
    D365Service,
    normalize,
)

BUNDLE = ROOT / "d365"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def validate_dto(value, name, contracts):
    check(isinstance(value, dict), f"{name}: expected an object")
    members = contracts[name]["members"]
    check(set(value) == set(members), f"{name}: example fields differ from the DTO")
    for field, kind in members.items():
        item = value[field]
        if kind.startswith("List<"):
            check(isinstance(item, list), f"{name}.{field}: expected an array")
            for row in item:
                validate_dto(row, kind[5:-1], contracts)
        elif kind in contracts:
            if item is not None:
                validate_dto(item, kind, contracts)
        else:
            valid = {
                "str": isinstance(item, str),
                "int": type(item) is int,
                "real": type(item) in (int, float),
                "boolean": type(item) is bool,
            }[kind]
            check(valid, f"{name}.{field}: wrong JSON type for {kind}")


def validate_sources(manifest, schema):
    contracts = manifest["contracts"]
    for name, contract in contracts.items():
        source = (ROOT / contract["source"]).read_text(encoding="utf-8")
        check(f"class {name}" in source, f"Wrong class declaration: {name}")
        found = re.findall(r'DataMemberAttribute\("([^"]+)"\)', source)
        check(len(found) == len(set(found)), f"Duplicate DTO member in {name}")
        check(set(found) == set(contract["members"]), f"Manifest differs from {name}")
        accessors = re.findall(
            r'DataMemberAttribute\("([^"]+)"\).*?public\s+(\w+)\s+(parm\w+)\(',
            source, flags=re.DOTALL,
        )
        for member, return_type, _accessor in accessors:
            expected = contract["members"][member].split("<", 1)[0]
            check(return_type == expected, f"Wrong X++ return type for {name}.{member}")
        for target in contract["members"].values():
            if target.startswith("List<"):
                row_type = target[5:-1]
                check(f"classStr({row_type})" in source, f"Untyped list in {name}")

    request = contracts["UBHRPortalRequestContract"]["members"]
    check(set(REQUEST_FIELDS.values()) <= set(request), "Backend request alias missing in DTO")
    service = (BUNDLE / "xpp/UBHRPortalService.xpp").read_text(encoding="utf-8")
    request_source = (ROOT / contracts["UBHRPortalRequestContract"]["source"]).read_text(encoding="utf-8")
    request_accessors = set(re.findall(r"public\s+\w+\s+(parm\w+)\(", request_source))
    check(set(re.findall(r"_request\.(parm\w+)\(", service)) <= request_accessors,
          "Service refers to a missing request accessor")
    check(service.count("[SysEntryPointAttribute(true)]") == 6, "Expected six entry points")
    for operation, info in manifest["operations"].items():
        parameter = "" if info["request"] is None else f'{info["request"]} _request'
        signature = f'public {info["response"]} {operation}({parameter})'
        check(signature in service, f"Operation signature mismatch: {operation}")

    table_types = "|".join(schema["tables"])
    declarations = re.findall(rf"\b({table_types})\s+(\w+)", service)
    system = set(schema["system_fields"]["automatic"])
    system.update(schema["system_fields"]["enabled_by_table_properties"])
    for table, variable in set(declarations):
        fields = {field["name"] for field in schema["tables"][table]["fields"]} | system
        used = set(re.findall(rf"\b{variable}\.([A-Za-z]\w*)\b(?!\s*\()", service))
        check(used <= fields, f"Unknown {table} fields: {used - fields}")

    for table, spec in schema["tables"].items():
        fields = {field["name"] for field in spec["fields"]}
        check(len(fields) == len(spec["fields"]), f"Duplicate field in {table}")
        for field in spec["fields"]:
            edt = field.get("extended_data_type")
            enum = field.get("enum_type")
            if edt:
                check(edt in schema["edts"] or edt in schema["standard_edts"],
                      f"Unknown EDT for {table}.{field['name']}")
            if enum:
                check(enum in schema["enums"] or enum == "NoYes",
                      f"Unknown enum for {table}.{field['name']}")
        for index in spec["indexes"]:
            check(set(index["fields"]) <= fields | system, f"Unknown index field in {table}")
        for relation in spec["relations"]:
            related = schema["tables"][relation["related_table"]]
            related_fields = {field["name"] for field in related["fields"]} | system
            check(relation["field"] in fields and relation["related_field"] in related_fields,
                  f"Unknown relation field in {table}")
        replacement = next(index for index in spec["indexes"]
                           if index["name"] == spec["properties"]["ReplacementKey"])
        check(not replacement["allow_duplicates"] and replacement["alternate_key"],
              f"Invalid replacement key in {table}")
        check(spec["properties"]["SaveDataPerCompany"] == "Yes", f"Unscoped table: {table}")


def canonical_request(body):
    """Reverse the documented wire example into the backend's canonical payload."""
    reverse = {}
    for canonical, external in REQUEST_FIELDS.items():
        reverse.setdefault(external, canonical)
    payload = {}
    for external, value in body.items():
        canonical = reverse[external]
        if canonical in MEMO_FIELDS:
            value = normalize(json.loads(value))
        elif canonical == "linkedin_profile":
            value = json.loads(value)
            LinkedInProfile.model_validate(value)
        payload[canonical] = value
    return payload


async def validate_adapter(manifest):
    requests = {}
    responses = {}
    operations = manifest["operations"]
    contracts = manifest["contracts"]
    for name, info in operations.items():
        requests[name] = read_json(BUNDLE / f"examples/{name}.request.json")
        responses[name] = read_json(BUNDLE / f"examples/{name}.response.json")
        validate_dto(responses[name], info["response"], contracts)
        if info["request"] is None:
            check(requests[name] == {}, f"{name} must be parameterless")
        else:
            check(set(requests[name]) == {"_request"}, f"Wrong wrapper for {name}")
            check(set(requests[name]["_request"]) <= set(contracts[info["request"]]["members"]),
                  f"Unknown request member in {name}")

    company = requests["submitApplication"]["_request"]["Company"]
    settings = SimpleNamespace(d365_company=company, d365_parameter_name="_request",
                               d365_base_url="https://fo.example.invalid", d365_http_timeout=30,
                               d365_request_wrappers={}, d365_request_field_maps={},
                               d365_response_field_maps={})
    for operation, info in operations.items():
        setattr(settings, PATHS[info["backend_operation"]],
                f'/api/services/{manifest["service_group"]}/{manifest["aot_service"]}/{operation}')

    seen = []

    def respond(request):
        name = request.url.path.rsplit("/", 1)[-1]
        check(request.method == "POST", f"{name}: wrong method")
        check(json.loads(request.content) == requests[name], f"{name}: actual adapter body differs")
        seen.append(name)
        return httpx.Response(200, json=responses[name])

    class FixtureService(D365Service):
        async def get_access_token(self, force_refresh=False):
            return "local-mocked-token"

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service = FixtureService(settings, client=client)
        jobs = await service.get_open_requirements()
        check(all(job.status == "Open" for job in jobs), "Invalid job status")
        # Examples may become past-deadline documents. Validate the complete
        # job shape independently of the adapter's time-dependent eligibility.
        for row in normalize(responses["getOpenRequirements"])["requirements"]:
            for field in ("required_skills", "preferred_skills", "required_certifications"):
                row[field] = [part.strip() for part in re.split(r"[,;\n]", row[field]) if part.strip()]
            Job.model_validate(row)

        submission = canonical_request(requests["submitApplication"]["_request"])
        submission.pop("company")
        acknowledgement = await service.submit_application(submission)
        application_id = acknowledgement["application_id"]
        evaluation_request = requests["saveCandidateEvaluation"]["_request"]
        evaluation_fields = {key: value for key, value in normalize(evaluation_request).items()
                             if key in Evaluation.model_fields}
        evaluation = Evaluation.model_validate(evaluation_fields)
        await service.save_candidate_evaluation({
            "application_id": application_id, "requirement_id": evaluation_request["RequirementId"],
            "evaluation_date": evaluation_request["EvaluatedDateTime"], "evaluation": evaluation,
        })
        top_request = requests["getTopCandidates"]["_request"]
        candidates = await service.get_top_candidates(top_request["RequirementId"], top_request["Limit"])
        check(candidates[0].evaluation.score == evaluation.score, "Score was changed")
        check(any(candidate.evaluation is None for candidate in candidates), "Missing pending example")

        mine = requests["getMyApplications"]["_request"]
        user = User(sub=mine["LinkedInSub"], issuer=mine["LinkedInIssuer"],
                    name="Alex Example", email="alex.example@example.com", role="candidate")
        history = await service.get_my_applications(user)
        check(all(row.owner_sub == user.sub and row.owner_issuer == user.issuer for row in history),
              "History ownership mismatch")
        detail = await service.get_application(application_id)
        check(detail.evaluation.score == evaluation.score, "Detail score mismatch")
        check(detail.evaluation_date == evaluation_request["EvaluatedDateTime"], "Timestamp mismatch")
    check(set(seen) == set(operations), "Not all six actual adapter operations ran")


def validate_postman(manifest):
    collection = read_json(BUNDLE / "UBHRPortal.postman_collection.json")
    check(len(collection["item"]) == 6, "Postman must expose all six operations")
    variables = {item["key"]: item["value"] for item in collection["variable"]}
    check(not variables.get("accessToken"), "Postman must not include a token")
    for item in collection["item"]:
        request = item["request"]
        check(request["method"] == "POST", "Postman service request must use POST")
        raw = request["url"] if isinstance(request["url"], str) else request["url"]["raw"]
        operation = raw.rsplit("/", 1)[-1]
        check(operation in manifest["operations"], "Unknown Postman operation")
        check(f'/{manifest["service_group"]}/{manifest["aot_service"]}/' in raw,
              "Postman endpoint differs from the source")
        body = request["body"]["raw"]
        for key, value in variables.items():
            body = body.replace("{{" + key + "}}", str(value))
        json.loads(body)


def main():
    manifest = read_json(BUNDLE / "contracts-manifest.json")
    schema = read_json(BUNDLE / "table-specification.json")
    validate_sources(manifest, schema)
    asyncio.run(validate_adapter(manifest))
    validate_postman(manifest)
    print("PASS: metadata references, DTOs, 12 fixtures, six actual backend adapter operations, Postman")
    print("X++ compilation, database synchronization, permissions and live F&O calls remain unverified.")


if __name__ == "__main__":
    main()
