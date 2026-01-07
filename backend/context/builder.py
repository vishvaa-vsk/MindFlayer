"""Context builder for parsing requirements text into SystemContext."""
import re
from models.context import Endpoint, AuthRule, SystemContext
from context.llm_parser import parse_prose_to_structured


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

    LLM Flow:
    - Detects if input is prose (natural language)
    - Uses OpenAI to convert prose → structured format
    - Falls back to regex parsing

    Args:
        text: Requirements text (prose or structured)

    Returns:
        SystemContext object with parsed endpoints

    Raises:
        ValueError: If requirements are malformed or LLM fails
    """
    # Check if text is already structured or needs LLM parsing
    if not is_structured_format(text):
        # Use LLM to convert prose to structured format
        try:
            text = parse_prose_to_structured(text)
        except ValueError as e:
            # If API key not set, try regex parsing anyway
            if "OPENAI_API_KEY" in str(e):
                raise ValueError(
                    f"Natural language parsing requires OpenAI API key. {str(e)}\n"
                    f"Alternatively, use structured format: METHOD /path (requires auth)"
                )
            raise

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

    return SystemContext(
        endpoints=endpoints,
        auth_rules=auth_rules,
        dependencies=dependencies,
    )
