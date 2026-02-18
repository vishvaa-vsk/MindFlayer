"""LLM-based natural language requirements parser using the adapter layer."""
import json
import logging
import re

from config import get_settings
from adapters.registry import get_adapter

logger = logging.getLogger(__name__)


def _clean_llm_output(text: str) -> str:
    """Strip <think> tags, markdown code fences, and other LLM artifacts."""
    if not text:
        return text

    # Remove <think>...</think> blocks (greedy across newlines)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # Remove markdown code fences (```...\n and trailing ```)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            continue
        cleaned.append(line)
    text = '\n'.join(cleaned)

    return text.strip()


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
        {"role": "system", "content": "You are an API design expert. Convert natural language requirements to structured REST API endpoints. Return ONLY the endpoint lines, nothing else."},
        {"role": "user", "content": prompt},
    ]

    # Try up to 2 times — some free models return empty on first attempt
    for attempt in range(2):
        try:
            result = adapter.chat(
                messages=messages,
                model=settings.parsing_model,
                temperature=settings.parsing_temperature + (0.1 * attempt),  # Slightly higher temp on retry
                max_tokens=1000,
            )

            cleaned = _clean_llm_output(result)

            # Validate: check if output contains at least one structured endpoint line
            if cleaned and re.search(r'^[A-Z]+\s+/', cleaned, re.MULTILINE):
                return cleaned

            logger.warning(
                "[parse_prose] Attempt %d: LLM returned no valid endpoints (raw length=%d, cleaned length=%d)",
                attempt + 1, len(result), len(cleaned),
            )
        except Exception as e:
            logger.warning("[parse_prose] Attempt %d: LLM call failed: %s", attempt + 1, str(e)[:150])

    # All LLM attempts failed — try deterministic keyword fallback
    logger.warning("[parse_prose] LLM failed after 2 attempts, using keyword-based fallback parser")
    fallback = _keyword_fallback_parser(prose)
    if fallback:
        return fallback

    # Nothing worked — raise a clear error
    raise ValueError(
        "Could not convert your requirements to API endpoints. "
        "The LLM returned empty output and keyword extraction found no resources. "
        "Try using structured format instead (e.g., 'POST /orders (requires user_auth)') "
        "or switch to a different parsing model in Settings."
    )


def _keyword_fallback_parser(prose: str) -> str:
    """
    Deterministic keyword-based prose parser.

    Extracts resource nouns and generates standard CRUD endpoints.
    Used when LLM parsing fails or returns empty.

    Args:
        prose: Natural language requirements text

    Returns:
        Structured endpoints string, or empty string if no resources found
    """
    prose_lower = prose.lower()

    # ── Detect auth requirements ──
    has_auth = any(kw in prose_lower for kw in [
        "auth", "login", "sign in", "signin", "register", "sign up", "signup",
        "token", "session", "password", "credential", "permission",
        "authenticated", "logged in",
    ])
    has_admin = any(kw in prose_lower for kw in [
        "admin", "administrator", "moderator", "superuser", "manage",
    ])

    # ── Extract resource nouns from common patterns ──
    # Look for action + resource patterns
    resource_patterns = [
        # "create/add/manage/view/list/delete/update/cancel Xes/Xs"
        r'\b(?:create|add|manage|view|list|delete|update|cancel|edit|remove|get|fetch|read|submit|process|place|send|make)\s+(?:a\s+|an\s+|the\s+|their\s+|all\s+|new\s+|pending\s+)?(\w+)',
        # "X management" or "X processing"
        r'\b(\w+)\s+(?:management|processing|listing|creation|registration|tracking|history)',
        # "Xs can be created/updated/deleted"
        r'\b(\w+)\s+can\s+be\s+(?:created|updated|deleted|viewed|listed|cancelled)',
    ]

    raw_resources = set()
    for pattern in resource_patterns:
        for match in re.finditer(pattern, prose_lower):
            word = match.group(1).strip()
            # Skip noise words
            if word in {'a', 'an', 'the', 'their', 'all', 'new', 'up', 'in', 'out',
                        'it', 'this', 'that', 'can', 'should', 'must', 'will', 'with',
                        'from', 'into', 'for', 'and', 'or', 'is', 'are', 'be', 'to',
                        'system', 'users', 'user', 'api', 'data', 'information'}:
                continue
            if len(word) < 3:
                continue
            raw_resources.add(word)

    # Singularize and deduplicate
    resources = set()
    for r in raw_resources:
        singular = r.rstrip('s') if r.endswith('s') and len(r) > 4 and not r.endswith('ss') else r
        resources.add(singular)

    # Always add users if auth is mentioned
    if has_auth:
        resources.add('user')

    if not resources:
        return ""

    # ── Generate CRUD endpoints ──
    lines = []
    auth_suffix = " (requires user_auth)" if has_auth else ""
    admin_suffix = " (requires admin_auth)" if has_admin else ""

    # Determine which resources need auth vs admin
    admin_keywords = {'product', 'item', 'catalog', 'setting', 'config', 'role'}

    for resource in sorted(resources):
        plural = resource + 's' if not resource.endswith('s') else resource
        path = f"/{plural}"

        # Check if this resource has a dependency on user
        depends = ""
        if resource not in ('user',) and has_auth:
            depends = ""  # Simple: no depends for fallback

        # Determine auth type for this resource
        is_admin_resource = resource in admin_keywords
        res_auth = admin_suffix if is_admin_resource else auth_suffix

        # Check for specific verbs associated with this resource
        has_create = any(kw in prose_lower for kw in [f'create {plural}', f'create {resource}',
                                                       f'add {plural}', f'add {resource}',
                                                       f'place {plural}', f'place {resource}',
                                                       f'submit {plural}', f'submit {resource}',
                                                       f'register', f'sign up'])
        has_view = any(kw in prose_lower for kw in [f'view {plural}', f'view {resource}',
                                                     f'get {plural}', f'get {resource}',
                                                     f'list {plural}', f'list {resource}',
                                                     f'read {plural}', f'read {resource}',
                                                     f'{resource} history', f'their {plural}',
                                                     f'all {plural}'])
        has_delete = any(kw in prose_lower for kw in [f'delete {plural}', f'delete {resource}',
                                                       f'cancel {plural}', f'cancel {resource}',
                                                       f'remove {plural}', f'remove {resource}'])
        has_update = any(kw in prose_lower for kw in [f'update {plural}', f'update {resource}',
                                                       f'edit {plural}', f'edit {resource}',
                                                       f'modify {plural}', f'modify {resource}'])

        # Default: if no specific verbs found, generate all CRUD
        if not any([has_create, has_view, has_delete, has_update]):
            has_create = True
            has_view = True

        if has_create:
            lines.append(f"POST {path}{res_auth}")
        if has_view:
            lines.append(f"GET {path}{res_auth}")
            lines.append(f"GET {path}/:id{res_auth}")
        if has_update:
            lines.append(f"PUT {path}/:id{res_auth}")
        if has_delete:
            lines.append(f"DELETE {path}/:id{res_auth}")

    # Add auth endpoints if auth is detected
    if has_auth:
        if 'user' in resources:
            # Check if register/login explicitly mentioned
            if any(kw in prose_lower for kw in ['register', 'sign up', 'signup']):
                lines.insert(0, "POST /register")
            if any(kw in prose_lower for kw in ['login', 'sign in', 'signin']):
                lines.insert(0 if 'POST /register' not in lines else 1, "POST /login")

    result = "\n".join(lines)
    logger.info("[parse_prose] Keyword fallback generated %d endpoints from %d resources", len(lines), len(resources))
    return result


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

        # Clean LLM artifacts (think tags, code fences, etc.)
        result = _clean_llm_output(result)

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return get_generic_payload(endpoint_path, endpoint_method)
    except Exception:
        return get_generic_payload(endpoint_path, endpoint_method)


def generate_tests_batch_with_llm(scenarios: list[dict]) -> dict[str, str]:
    """
    Generate multiple pytest test functions in a single LLM call.

    Instead of 1 API call per scenario, this batches multiple scenarios
    into one prompt — reducing 26 calls to 2-3 calls.

    Args:
        scenarios: List of dicts with keys:
            test_name, endpoint_method, endpoint_path, test_type,
            description, requires_auth, depends_on

    Returns:
        Dict mapping test_name → generated test code string.
        Missing keys mean that scenario wasn't successfully parsed from output.
    """
    if not scenarios:
        return {}

    settings = get_settings()

    try:
        adapter = get_adapter()
    except Exception:
        return {}

    if not settings.has_api_key and settings.llm_provider in ("openrouter", "azure"):
        return {}

    # Build a compact description of all scenarios
    scenario_lines = []
    for i, s in enumerate(scenarios, 1):
        test_path = s["endpoint_path"].replace(":id", "test-id-123")
        auth_str = "yes" if s.get("requires_auth") else "no"
        deps = s.get("depends_on") or []
        scenario_lines.append(
            f"{i}. test_{s['test_name']} | {s['endpoint_method']} {test_path} | "
            f"type={s['test_type']} | auth={auth_str} | deps={deps} | {s['description']}"
        )

    scenarios_block = "\n".join(scenario_lines)

    prompt = f"""Write {len(scenarios)} pytest test functions for these API test scenarios:

{scenarios_block}

Rules:
1. Use `client` fixture (httpx TestClient) — already available
2. Use client.get(), client.post(), client.put(), client.delete()
3. Include realistic payloads for POST/PUT
4. Add meaningful assertions (status codes + response body)
5. Include a docstring in each function
6. For positive tests: expect 200 or 201
7. For no_auth tests: omit auth headers, expect 401 or 403
8. For dependency_failure tests: skip dependency setup, expect 400/404/409/422
9. For invalid_input tests: use "nonexistent-id-999", expect 404
10. For auth-required endpoints, use `auth_headers` fixture
11. Return ONLY the function code — no imports, no fixtures, no markdown

Write all {len(scenarios)} functions separated by blank lines:"""

    messages = [
        {"role": "system", "content": "You are a senior test engineer. Write clean pytest functions for REST API testing. Return ONLY the function code, no markdown fences, no explanations. Separate functions with blank lines."},
        {"role": "user", "content": prompt},
    ]

    try:
        # Use higher max_tokens for batch — ~200 tokens per test
        max_tokens = min(len(scenarios) * 250, 4096)
        code = adapter.chat(
            messages=messages,
            model=settings.generation_model,
            temperature=settings.generation_temperature,
            max_tokens=max_tokens,
        )

        code = _clean_llm_output(code)
        if not code or "def test_" not in code:
            logger.warning("[batch_gen] LLM returned no valid test functions")
            return {}

        # Parse individual test functions from the batch output
        return _parse_batch_output(code, [s["test_name"] for s in scenarios])

    except Exception as e:
        logger.warning("[batch_gen] Batch LLM call failed: %s", str(e)[:150])
        return {}


def _parse_batch_output(code: str, expected_names: list[str]) -> dict[str, str]:
    """
    Parse batch LLM output into individual test functions.

    Splits on 'def test_' boundaries and maps each function to its test name.

    Args:
        code: Raw LLM output containing multiple test functions
        expected_names: List of expected test_name values (without 'test_' prefix)

    Returns:
        Dict mapping test_name → function code string
    """
    results = {}

    # Split on function boundaries
    parts = re.split(r'(?=\ndef test_|\A\s*def test_)', code)
    functions = [p.strip() for p in parts if p.strip().startswith("def test_")]

    # Build a lookup from function name to code
    func_lookup = {}
    for func_code in functions:
        match = re.match(r'def (test_\w+)', func_code)
        if match:
            func_lookup[match.group(1)] = func_code

    # Map expected names to parsed functions
    for name in expected_names:
        full_name = f"test_{name}"
        if full_name in func_lookup:
            results[name] = func_lookup[full_name]
        else:
            # Try fuzzy match — LLM might have slightly different naming
            for fn, fc in func_lookup.items():
                if name.replace("-", "_") in fn or fn.replace("test_", "") == name:
                    results[name] = fc
                    break

    logger.info(
        "[batch_gen] Parsed %d/%d test functions from LLM batch output",
        len(results), len(expected_names),
    )
    return results


def generate_test_code_with_llm(test_name: str, endpoint_name: str, endpoint_method: str,
                                  endpoint_path: str, test_type: str, description: str,
                                  requires_auth: bool = False, depends_on: list[str] | None = None) -> str:
    """
    Use LLM to generate intelligent, realistic pytest test code.
    (Single-scenario fallback — prefer generate_tests_batch_with_llm for speed.)

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

        # Clean LLM artifacts (think tags, code fences, etc.)
        code = _clean_llm_output(code)

        # Validate the output looks like a Python function
        if not code or "def test_" not in code:
            logger.debug("LLM code generation returned invalid output, falling back to template")
            return ""

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
