"""LLM-based natural language requirements parser using the adapter layer."""
import json
import logging

from config import get_settings
from adapters.registry import get_adapter

logger = logging.getLogger(__name__)


def parse_prose_to_structured(prose: str) -> str:
    """
    Convert natural language requirements to structured format using LLM.

    Takes prose like:
        "Users can create orders with items. Authentication required."

    Returns structured format:
        POST /orders (requires user_auth)
        GET /orders/:id (requires user_auth, depends on POST /orders)

    Args:
        prose: Natural language requirements text

    Returns:
        Structured requirements string (METHOD /path format)
    """
    settings = get_settings()
    adapter = get_adapter()

    prompt = f"""You are an API design expert. Convert the following natural language requirements into structured API endpoints.

Format: METHOD /path (requires auth_type, depends on OTHER_METHOD /other_path)

Examples:
- POST /orders (requires user_auth)
- GET /orders/:id (requires user_auth, depends on POST /orders)
- DELETE /orders/:id (requires user_auth)

Rules:
1. Use RESTful conventions (GET, POST, PUT, DELETE)
2. Use :id for path parameters
3. Include "requires X_auth" if authentication is mentioned
4. Include "depends on Y endpoint" if one endpoint needs another
5. Return ONLY the structured format, one endpoint per line
6. Do NOT include explanations or comments

Requirements:
{prose}

Structured endpoints:"""

    messages = [
        {"role": "system", "content": "You are an API design expert. Convert natural language requirements to structured REST API endpoints."},
        {"role": "user", "content": prompt},
    ]

    return adapter.chat(
        messages=messages,
        model=settings.parsing_model,
        temperature=settings.parsing_temperature,
        max_tokens=1000,
    )


def generate_smart_payload(endpoint_path: str, endpoint_method: str, description: str = "") -> dict:
    """
    Generate realistic test payload using LLM.

    Args:
        endpoint_path: API path like /orders or /orders/:id
        endpoint_method: HTTP method
        description: Endpoint description/purpose

    Returns:
        Dictionary with realistic test data
    """
    settings = get_settings()

    try:
        adapter = get_adapter()
    except Exception:
        return get_generic_payload(endpoint_path, endpoint_method)

    if not settings.has_api_key and settings.llm_provider in ("openrouter", "azure"):
        return get_generic_payload(endpoint_path, endpoint_method)

    prompt = f"""Generate a realistic JSON payload for testing this API endpoint:

Method: {endpoint_method}
Path: {endpoint_path}
Description: {description}

Requirements:
1. Return ONLY valid JSON object
2. Use realistic, meaningful test data
3. Include relevant fields based on the endpoint
4. Do NOT include explanations
5. Use snake_case for field names
6. Use realistic types (strings, numbers, objects, arrays)

Examples:
- For POST /orders: {{"user_id": "uuid-123", "items": [{{"product_id": "P001", "quantity": 2}}], "total": 99.99}}
- For POST /users: {{"name": "John Doe", "email": "john@example.com", "phone": "+1234567890"}}

Generate payload:"""

    messages = [
        {"role": "system", "content": "You are a test data generation expert. Generate realistic JSON payloads for API testing."},
        {"role": "user", "content": prompt},
    ]

    try:
        result = adapter.chat(
            messages=messages,
            model=settings.parsing_model,
            temperature=0.5,
            max_tokens=500,
        )

        # Strip markdown code fences if present
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return get_generic_payload(endpoint_path, endpoint_method)
    except Exception:
        return get_generic_payload(endpoint_path, endpoint_method)


def generate_test_code_with_llm(test_name: str, endpoint_name: str, endpoint_method: str,
                                  endpoint_path: str, test_type: str, description: str,
                                  requires_auth: bool = False, depends_on: list[str] | None = None) -> str:
    """
    Use LLM to generate intelligent, realistic pytest test code.

    Args:
        test_name: Name of the test function
        endpoint_name: Internal endpoint identifier
        endpoint_method: HTTP method (GET, POST, etc.)
        endpoint_path: URL path (/orders, /orders/:id, etc.)
        test_type: Type of test (positive, no_auth, dependency_failure, invalid_input)
        description: Human-readable test description
        requires_auth: Whether the endpoint requires authentication
        depends_on: List of dependent endpoint names

    Returns:
        String containing the complete pytest test function code
    """
    settings = get_settings()

    try:
        adapter = get_adapter()
    except Exception:
        return ""  # Fallback to template-based generation

    if not settings.has_api_key and settings.llm_provider in ("openrouter", "azure"):
        return ""

    # Build the test path for client calls
    test_path = endpoint_path.replace(":id", "test-id-123")

    prompt = f"""Write a single pytest test function for this API test scenario:

Test name: test_{test_name}
HTTP method: {endpoint_method}
Endpoint path: {endpoint_path}
Test type: {test_type}
Description: {description}
Requires auth: {requires_auth}
Dependencies: {depends_on or []}

Rules:
1. Use `client` as an already-available fixture (httpx TestClient)
2. Use `client.get()`, `client.post()`, `client.put()`, `client.delete()` etc.
3. Use the actual endpoint path: {test_path}
4. Include realistic test data in payloads
5. Add meaningful assertions (status codes, response body checks)
6. Include descriptive docstring
7. Return ONLY the function code, no imports or fixtures
8. For positive tests: expect 200 or 201
9. For no_auth tests: omit auth headers, expect 401 or 403
10. For dependency_failure tests: skip creating the dependency, expect 400/404/409/422
11. For invalid_input tests: use invalid IDs like "nonexistent-id-999", expect 404

Write the pytest function:"""

    messages = [
        {"role": "system", "content": "You are a senior test engineer. Write clean pytest test functions for REST API testing. Return ONLY code, no markdown fences or explanations."},
        {"role": "user", "content": prompt},
    ]

    try:
        code = adapter.chat(
            messages=messages,
            model=settings.generation_model,
            temperature=settings.generation_temperature,
            max_tokens=600,
        )

        # Strip markdown code fences if present
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return code
    except Exception as e:
        # Log timeout and other errors, then fall back to template generation
        logger.debug(f"LLM code generation failed (falling back to template): {str(e)[:100]}")
        return ""  # Fallback to template


def get_generic_payload(endpoint_path: str, endpoint_method: str) -> dict:
    """
    Generate domain-aware payload when LLM is unavailable.

    Uses schema inference to produce realistic field names (email, password, etc.)
    instead of generic templates like {resource}_name.

    Args:
        endpoint_path: API path
        endpoint_method: HTTP method

    Returns:
        Realistic payload dictionary
    """
    if endpoint_method in ["POST", "PUT", "PATCH"]:
        from models.context import Endpoint
        from context.schema_inference import infer_schemas, fields_to_payload

        # Create a temporary endpoint for inference
        ep = Endpoint(name="temp", method=endpoint_method, url_path=endpoint_path)
        infer_schemas([ep])
        if ep.request_body:
            return fields_to_payload(ep.request_body)

        # Absolute fallback (should rarely reach here)
        return {"name": "Test Item", "description": "Test description"}
    return {}
