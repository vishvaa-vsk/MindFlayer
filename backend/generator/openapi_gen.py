"""OpenAPI 3.0 specification generator with test extensions.

Uses FieldSpec metadata from endpoints to produce realistic, domain-aware
request/response schemas instead of generic templates.
"""
import yaml
from models.test_plan import TestPlan
from models.context import SystemContext, FieldSpec


def generate_openapi_spec(test_plan: TestPlan, context: SystemContext | None = None) -> str:
    """
    Generate an OpenAPI 3.0 spec with x-tests extension from a test plan.

    Uses enriched endpoint metadata (FieldSpec, StateConstraint) to produce
    realistic schemas. Falls back to generic schemas if metadata is absent.

    Args:
        test_plan: TestPlan with scenarios
        context: SystemContext for endpoint metadata

    Returns:
        OpenAPI 3.0 YAML string
    """
    endpoint_lookup = {}
    auth_types = set()
    if context:
        for ep in context.endpoints:
            endpoint_lookup[ep.name] = ep
            if ep.requires_auth:
                auth_types.add("bearerAuth")

    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "MindFlayer Generated API Spec",
            "description": f"Auto-generated OpenAPI specification with test coverage.\\n\\n{test_plan.rationale}",
            "version": "1.0.0",
            "x-generator": "MindFlayer",
        },
        "servers": [
            {"url": "http://localhost:8000", "description": "Local development"},
        ],
        "paths": {},
    }

    # Security schemes
    if auth_types:
        spec["components"] = {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT Bearer token authentication",
                },
            },
        }

    # Group scenarios by endpoint
    endpoint_scenarios: dict[str, list] = {}
    for scenario in test_plan.scenarios:
        if scenario.endpoint not in endpoint_scenarios:
            endpoint_scenarios[scenario.endpoint] = []
        endpoint_scenarios[scenario.endpoint].append(scenario)

    for endpoint_name, scenarios in endpoint_scenarios.items():
        ep = endpoint_lookup.get(endpoint_name)
        method = ep.method.lower() if ep else "get"
        path = ep.url_path if ep else "/"

        # Convert :id to {id} for OpenAPI
        openapi_path = path.replace(":id", "{id}")

        if openapi_path not in spec["paths"]:
            spec["paths"][openapi_path] = {}

        operation = {
            "summary": _humanize_name(endpoint_name),
            "operationId": endpoint_name,
            "tags": [_extract_resource(path)],
        }

        # Add description if available
        if ep and ep.description:
            operation["description"] = ep.description

        # Parameters
        if "{id}" in openapi_path:
            operation["parameters"] = [{
                "name": "id",
                "in": "path",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
                "description": "Resource identifier",
            }]

        # Request body for write methods — uses FieldSpec metadata
        if method in ("post", "put", "patch"):
            operation["requestBody"] = _build_request_body(ep)

        # Security
        if ep and ep.requires_auth:
            operation["security"] = [{"bearerAuth": []}]

        # Responses from test types + expected_status
        responses = {}
        for scenario in scenarios:
            code = str(scenario.expected_status)
            if code not in responses:
                responses[code] = {
                    "description": _get_status_description(code),
                }
            # Add additional status codes from test type
            for extra_code in _get_extra_status_codes(scenario.test_type):
                if extra_code not in responses:
                    responses[extra_code] = {
                        "description": _get_status_description(extra_code),
                    }

        # Ensure at least a success response exists
        success_code = str(ep.expected_success_code) if ep else "200"
        if success_code not in responses:
            responses[success_code] = {
                "description": _get_status_description(success_code),
            }
            # Add response body schema for success
            if ep and ep.response_body:
                responses[success_code]["content"] = {
                    "application/json": {
                        "schema": _fields_to_schema(ep.response_body),
                    },
                }

        operation["responses"] = dict(sorted(responses.items()))

        # x-tests extension
        operation["x-tests"] = [
            {
                "name": f"test_{s.test_name}",
                "type": s.test_type,
                "description": s.description,
                "expected_status": s.expected_status,
            }
            for s in scenarios
        ]

        spec["paths"][openapi_path][method] = operation

    return yaml.dump(spec, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _build_request_body(ep) -> dict:
    """Build OpenAPI requestBody from endpoint FieldSpecs."""
    if ep and ep.request_body:
        schema = _fields_to_schema(ep.request_body)
        return {
            "required": True,
            "content": {
                "application/json": {
                    "schema": schema,
                },
            },
        }

    # Fallback for endpoints without inferred schemas
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "example": "Test Item"},
                        "description": {"type": "string", "example": "Test description"},
                    },
                },
            },
        },
    }


def _fields_to_schema(fields: list[FieldSpec]) -> dict:
    """Convert FieldSpec list to OpenAPI schema object."""
    properties = {}
    required_fields = []

    for field in fields:
        properties[field.name] = field.to_openapi()
        if field.required:
            required_fields.append(field.name)

    schema = {"type": "object", "properties": properties}
    if required_fields:
        schema["required"] = required_fields
    return schema


def _humanize_name(name: str) -> str:
    """Convert endpoint_name to human-readable summary."""
    return name.replace("_", " ").title()


def _extract_resource(path: str) -> str:
    """Extract resource name from path (e.g., /orders/:id → orders)."""
    parts = path.strip("/").split("/")
    resource_parts = [p for p in parts if not p.startswith(":") and not p.startswith("{")]
    return resource_parts[0] if resource_parts else "resource"


def _get_extra_status_codes(test_type: str) -> list[str]:
    """Get additional status codes that should be documented for a test type."""
    return {
        "no_auth": ["401"],
        "dependency_failure": ["400"],
        "state_conflict": ["409"],
        "forbidden_role": ["403"],
        "field_validation": ["422"],
        "boundary_value": ["422"],
    }.get(test_type, [])


def _get_status_description(code: str) -> str:
    """Get standard HTTP status description."""
    return {
        "200": "Successful operation",
        "201": "Resource created successfully",
        "204": "Resource deleted successfully",
        "400": "Bad request — invalid input or missing fields",
        "401": "Unauthorized — authentication required",
        "403": "Forbidden — insufficient permissions",
        "404": "Not found — resource does not exist",
        "409": "Conflict — state constraint violated",
        "422": "Unprocessable entity — validation failed",
    }.get(code, "Response")
