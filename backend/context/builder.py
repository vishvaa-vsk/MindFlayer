"""Context builder for parsing requirements text into SystemContext."""
import re
from models.context import Endpoint, AuthRule, SystemContext
from context.llm_parser import parse_prose_to_structured
from context.schema_inference import infer_schemas


def is_structured_format(text: str) -> bool:
    """
    Check if text is already in structured format.

    Structured format has lines like: METHOD /path (requires auth)
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    structured_lines = [l for l in lines if re.match(r"^[A-Z]+\s+/", l)]
    return len(structured_lines) > 0


def parse_requirements_text(text: str) -> SystemContext:
    """
    Parse requirements text and extract endpoints into SystemContext.

    Supports two formats:
    1. Natural Language (Prose): Uses LLM to convert to structured format
    2. Structured Format: Direct parsing with regex
       Format: METHOD /path (requires auth_type, depends on OTHER /path)

    After parsing, runs schema inference to populate request/response bodies,
    state constraints, and roles on each endpoint.

    Args:
        text: Requirements text (prose or structured)

    Returns:
        SystemContext object with enriched endpoints

    Raises:
        ValueError: If requirements are malformed or LLM fails
    """
    original_text = text  # Keep for schema inference

    # Check if text is already structured or needs LLM parsing
    if not is_structured_format(text):
        # Use LLM to convert prose to structured format
        try:
            text = parse_prose_to_structured(text)
        except ValueError as e:
            raise
        except Exception as e:
            # LLM provider error — try keyword fallback built into parse_prose_to_structured
            raise ValueError(
                f"Failed to parse natural language requirements: {str(e)}\n"
                f"Use structured format: METHOD /path (requires auth)"
            )

    # Parse structured format (regex-based)
    endpoints = []
    auth_rules_dict = {}
    dependencies = {}

    lines = text.strip().split("\n")

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Extract HTTP method and path: "METHOD /path"
        method_path_match = re.match(
            r"^([A-Z]+)\s+(/[a-zA-Z0-9/:_-]*)", line
        )
        if not method_path_match:
            continue

        method = method_path_match.group(1)
        url_path = method_path_match.group(2)
        endpoint_name = f"{method}_{url_path}".lower().replace("/", "_").replace(":", "")

        # Extract auth requirement: "requires X_auth"
        requires_auth = False
        auth_scope = None
        auth_match = re.search(r"requires\s+(\w+_auth)", line)
        if auth_match:
            requires_auth = True
            auth_scope = auth_match.group(1)
            if auth_scope not in auth_rules_dict:
                auth_rules_dict[auth_scope] = []
            auth_rules_dict[auth_scope].append(endpoint_name)

        # Extract dependencies: "depends on METHOD /path"
        endpoint_depends = []
        depends_match = re.findall(r"depends on\s+([A-Z]+)\s+(/[a-zA-Z0-9/:_-]*)", line)
        for dep_method, dep_path in depends_match:
            dep_name = f"{dep_method}_{dep_path}".lower().replace("/", "_").replace(":", "")
            endpoint_depends.append(dep_name)

        # Deduplicate: if endpoint already exists, merge new info into it
        existing = next((e for e in endpoints if e.name == endpoint_name), None)
        if existing is not None:
            # Merge: promote auth if either line requires it
            if requires_auth and not existing.requires_auth:
                existing.requires_auth = True
            # Merge dependencies
            for dep in endpoint_depends:
                if dep not in existing.depends_on:
                    existing.depends_on.append(dep)
            # Merge into dependency map
            for dep in endpoint_depends:
                if dep not in dependencies.get(endpoint_name, []):
                    dependencies.setdefault(endpoint_name, []).append(dep)
            continue

        # Create Endpoint object
        endpoint = Endpoint(
            name=endpoint_name,
            method=method,
            url_path=url_path,
            requires_auth=requires_auth,
            depends_on=endpoint_depends,
        )
        endpoints.append(endpoint)
        dependencies[endpoint_name] = endpoint_depends

    # Build auth rules
    auth_rules = [AuthRule(scope=scope, required_for=endpoints_list)
                  for scope, endpoints_list in auth_rules_dict.items()]

    # ── Validate parsing produced results ─────────────────
    if not endpoints:
        raise ValueError(
            "No API endpoints could be parsed from the requirements. "
            "Please use structured format (e.g., 'POST /orders (requires user_auth)') "
            "or provide clearer natural language requirements. "
            "If using natural language, ensure your LLM provider is configured and responsive."
        )

    # ── Schema Inference ─────────────────────────────────
    # Enrich endpoints with request/response schemas, state constraints, and roles
    infer_schemas(endpoints, original_text)

    return SystemContext(
        endpoints=endpoints,
        auth_rules=auth_rules,
        dependencies=dependencies,
    )
