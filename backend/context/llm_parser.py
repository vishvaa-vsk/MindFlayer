"""LLM-based natural language requirements parser."""
import os
import json
from openai import OpenAI


def parse_prose_to_structured(prose: str) -> str:
    """
    Convert natural language requirements to structured format.

    Takes prose description like:
    "Users can create orders with items. Authentication required. 
    The system validates order totals against inventory."

    Returns structured format:
    POST /orders (requires user_auth)
    GET /orders/:id (requires user_auth, depends on POST /orders)
    ...

    Args:
        prose: Natural language requirements text

    Returns:
        Structured requirements string (METHOD /path format)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. "
            "Please set your OpenAI API key to use LLM parsing."
        )

    client = OpenAI(api_key=api_key)

    prompt = f"""
You are an API design expert. Convert the following natural language requirements into structured API endpoints.

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

Structured endpoints:
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Fast, cost-effective
        messages=[
            {"role": "system", "content": "You are an API design expert. Convert natural language requirements to structured REST API endpoints."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,  # Low temperature for consistency
        max_tokens=1000,
    )

    structured = response.choices[0].message.content.strip()
    return structured


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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Return generic payload if API key not set
        return get_generic_payload(endpoint_path, endpoint_method)

    client = OpenAI(api_key=api_key)

    prompt = f"""
Generate a realistic JSON payload for testing this API endpoint:

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

Generate payload:
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a test data generation expert. Generate realistic JSON payloads for API testing."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=500,
        )

        payload_str = response.choices[0].message.content.strip()
        
        # Try to parse as JSON
        try:
            return json.loads(payload_str)
        except json.JSONDecodeError:
            # If LLM output isn't valid JSON, return generic
            return get_generic_payload(endpoint_path, endpoint_method)
    except Exception:
        # Fallback to generic if API call fails
        return get_generic_payload(endpoint_path, endpoint_method)


def get_generic_payload(endpoint_path: str, endpoint_method: str) -> dict:
    """
    Generate generic payload when LLM is unavailable.

    Args:
        endpoint_path: API path
        endpoint_method: HTTP method

    Returns:
        Generic payload dictionary
    """
    if endpoint_method in ["POST", "PUT", "PATCH"]:
        # Extract resource name from path
        resource = endpoint_path.strip("/").split("/")[0]
        return {
            "id": "test-id-123",
            f"{resource[:-1]}_name": "Test Item",
            "created_at": "2025-01-01T00:00:00Z",
            "status": "active",
        }
    return {}
