"""Postman Collection v2.1 generator with domain-aware payloads."""
import json
import uuid
from models.test_plan import TestPlan
from models.context import SystemContext
from context.schema_inference import fields_to_payload


def generate_postman(test_plan: TestPlan, context: SystemContext | None = None) -> str:
    """
    Generate a Postman Collection v2.1 JSON from a test plan.

    Uses FieldSpec metadata from endpoints to produce realistic payloads
    (email, password, product_id, etc.) instead of generic templates.

    Args:
        test_plan: TestPlan with scenarios
        context: SystemContext for endpoint metadata

    Returns:
        Postman Collection JSON string
    """
    endpoint_lookup = {}
    if context:
        for ep in context.endpoints:
            endpoint_lookup[ep.name] = ep

    collection = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": "MindFlayer Generated Tests",
            "description": f"Auto-generated API test collection\\n\\n{test_plan.rationale}",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "base_url", "value": "http://localhost:8000", "type": "string"},
            {"key": "auth_token", "value": "Bearer test-token-valid", "type": "string"},
        ],
        "item": [],
    }

    # Group scenarios by endpoint
    endpoint_groups: dict[str, list] = {}
    for scenario in test_plan.scenarios:
        group = scenario.endpoint
        if group not in endpoint_groups:
            endpoint_groups[group] = []
        endpoint_groups[group].append(scenario)

    for endpoint_name, scenarios in endpoint_groups.items():
        ep = endpoint_lookup.get(endpoint_name)
        method = ep.method if ep else "GET"
        path = ep.url_path if ep else "/"

        folder = {
            "name": endpoint_name,
            "item": [],
        }

        for scenario in scenarios:
            test_path = path.replace(":id", "test-id-123")
            item = _build_request_item(scenario, method, test_path, ep)
            folder["item"].append(item)

        collection["item"].append(folder)

    return json.dumps(collection, indent=2)


def _build_request_item(scenario, method: str, test_path: str, ep) -> dict:
    """Build a single Postman request item from a test scenario."""
    requires_auth = ep.requires_auth if ep else False
    test_type = scenario.test_type

    # Build URL
    url_parts = test_path.strip("/").split("/")
    url = {
        "raw": "{{base_url}}" + test_path,
        "host": ["{{base_url}}"],
        "path": url_parts,
    }

    # Headers
    headers = [
        {"key": "Content-Type", "value": "application/json", "type": "text"},
    ]

    if test_type != "no_auth" and requires_auth:
        headers.append({
            "key": "Authorization",
            "value": "{{auth_token}}",
            "type": "text",
        })

    # Forbidden role: use a different auth token
    if test_type == "forbidden_role":
        headers = [h for h in headers if h["key"] != "Authorization"]
        headers.append({
            "key": "Authorization",
            "value": "Bearer forbidden-role-token",
            "type": "text",
            "description": "Token for unauthorized role",
        })

    # Body — uses FieldSpec-driven payloads
    body = None
    if method in ("POST", "PUT", "PATCH"):
        payload = _build_payload(scenario, ep, test_type)
        body = {
            "mode": "raw",
            "raw": json.dumps(payload, indent=4),
            "options": {"raw": {"language": "json"}},
        }

    # Test script
    test_script = _build_test_script(scenario, test_type)

    item = {
        "name": f"{scenario.test_name} ({test_type})",
        "request": {
            "method": method,
            "header": headers,
            "url": url,
            "description": scenario.description,
        },
        "event": [{
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": test_script,
            },
        }],
    }

    if body:
        item["request"]["body"] = body

    return item


def _build_payload(scenario, ep, test_type: str) -> dict:
    """Build realistic payload from endpoint FieldSpecs."""
    # Use payload_hint if provided
    if scenario.payload_hint:
        if ep and ep.request_body:
            base = fields_to_payload(ep.request_body)
            base.update(scenario.payload_hint)
            # Handle _omit_field
            omit = scenario.payload_hint.get("_omit_field")
            if omit and omit in base:
                del base[omit]
            base.pop("_omit_field", None)
            return base
        return scenario.payload_hint

    # FieldSpec-driven payload
    if ep and ep.request_body:
        payload = fields_to_payload(ep.request_body)

        if test_type == "invalid_input":
            # Corrupt the first field
            first_key = next(iter(payload), None)
            if first_key:
                payload[first_key] = "invalid-!@#$"

        if test_type == "field_validation":
            # Use invalid values for format fields
            for field in ep.request_body:
                if field.format == "email":
                    payload[field.name] = "not-an-email"
                elif field.format == "uuid":
                    payload[field.name] = "not-a-uuid"

        if test_type == "numeric_boundary":
            # Use hint values (negative quantity, zero, etc.)
            if scenario.payload_hint:
                payload.update(scenario.payload_hint)

        return payload

    # Absolute fallback
    return {"name": "Test Item", "description": "Test description"}


def _build_test_script(scenario, test_type: str) -> list[str]:
    """Generate pm.test() assertions using expected_status from scenario."""
    expected = scenario.expected_status
    lines = [
        f'// {scenario.description}',
    ]

    if test_type == "positive":
        lines.extend([
            f'pm.test("Status code is {expected}", function () {{',
            f'    pm.expect(pm.response.code).to.be.within(200, 299);',
            '});',
            '',
            'pm.test("Response has valid JSON body", function () {',
            '    pm.response.to.be.json;',
            '    var jsonData = pm.response.json();',
            '    pm.expect(jsonData).to.not.be.null;',
            '});',
        ])
    elif test_type == "no_auth":
        lines.extend([
            f'pm.test("Returns {expected} without auth", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
        ])
    elif test_type == "state_conflict":
        lines.extend([
            f'pm.test("Returns {expected} for state conflict", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
            '',
            'pm.test("Error message explains state violation", function () {',
            '    var jsonData = pm.response.json();',
            '    pm.expect(jsonData.detail || jsonData.message).to.be.a("string");',
            '});',
        ])
    elif test_type == "forbidden_role":
        lines.extend([
            f'pm.test("Returns {expected} for forbidden role", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
        ])
    elif test_type == "field_validation":
        lines.extend([
            f'pm.test("Returns {expected} for invalid field", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
            '',
            'pm.test("Response explains validation error", function () {',
            '    var jsonData = pm.response.json();',
            '    pm.expect(jsonData.detail || jsonData.errors).to.not.be.undefined;',
            '});',
        ])
    elif test_type == "boundary_value":
        lines.extend([
            f'pm.test("Returns {expected} for boundary violation", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
        ])
    elif test_type == "dependency_failure":
        lines.extend([
            f'pm.test("Returns {expected} when dependency not met", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
        ])
    elif test_type == "invalid_input":
        lines.extend([
            f'pm.test("Returns {expected} for invalid input", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
        ])
    elif test_type == "numeric_boundary":
        lines.extend([
            f'pm.test("Returns {expected} for numeric boundary violation", function () {{',
            f'    pm.expect(pm.response.code).to.equal({expected});',
            '});',
            '',
            'pm.test("Response explains validation error", function () {',
            '    var jsonData = pm.response.json();',
            '    pm.expect(jsonData.detail || jsonData.errors).to.not.be.undefined;',
            '});',
        ])

    return lines
