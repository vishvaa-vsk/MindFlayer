"""Context builder for parsing requirements text into SystemContext."""
import re
import logging
from models.context import (
    Endpoint, AuthRule, SystemContext, CodeContext, 
    FieldSpec, StateConstraint, BusinessRule
)
from context.llm_parser import parse_prose_to_structured
from context.schema_inference import infer_schemas
from context.code_analyzer import analyze_code_files

logger = logging.getLogger(__name__)


def is_structured_format(text: str) -> bool:
    """
    Check if text is already in structured format.

    Structured format has lines like: METHOD /path (requires auth)
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    structured_lines = [l for l in lines if re.match(r"^[A-Z]+\s+/", l)]
    return len(structured_lines) > 0


def parse_requirements_text(
    text: str,
    code_files: dict[str, str] | None = None,
    language: str = "python"
) -> SystemContext:
    """
    Parse requirements text and extract endpoints into SystemContext.

    Supports two formats:
    1. Natural Language (Prose): Uses LLM to convert to structured format
    2. Structured Format: Direct parsing with regex
       Format: METHOD /path (requires auth_type, depends on OTHER /path)

    After parsing, runs schema inference to populate request/response bodies,
    state constraints, and roles on each endpoint.

    Optionally analyzes source code files to extract real enums, validators,
    and business rules, which are then merged into the endpoint schemas.

    Args:
        text: Requirements text (prose or structured)
        code_files: Optional dict mapping filename -> file_content for code analysis
        language: Programming language of code files (default: "python")

    Returns:
        SystemContext object with enriched endpoints and code context

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

    # ── Code Context Analysis ────────────────────────────
    code_context = None
    if code_files:
        try:
            code_context = analyze_code_files(code_files, language=language)
            logger.info(
                f"Code analysis extracted: {len(code_context.enums)} enums, "
                f"{len(code_context.validators)} validators, "
                f"{len(code_context.business_rules)} business rules, "
                f"{len(code_context.models)} models"
            )
        except Exception as e:
            logger.warning(f"Failed to analyze code files: {e}")
            # Continue without code context
    
    # ── Schema Inference ─────────────────────────────────
    # Enrich endpoints with request/response schemas, state constraints, and roles
    infer_schemas(endpoints, original_text)
    
    # ── Merge Code Context into Endpoints ───────────────
    if code_context:
        _merge_code_context_into_endpoints(endpoints, code_context)

    return SystemContext(
        endpoints=endpoints,
        auth_rules=auth_rules,
        dependencies=dependencies,
        code_context=code_context,
    )


def _merge_code_context_into_endpoints(endpoints: list[Endpoint], code_context: CodeContext) -> None:
    """
    Merge code-derived context into endpoint schemas.
    
    This enriches endpoint request/response schemas with:
    - Real enum values from code
    - Validation constraints from Pydantic/SQLAlchemy models
    - Business rules as state constraints
    
    Args:
        endpoints: List of endpoints to enrich (modified in-place)
        code_context: Extracted code context
    """
    if not code_context:
        return
    
    for endpoint in endpoints:
        # ── Enrich request body fields with enum values ──
        for field in endpoint.request_body:
            _apply_code_context_to_field(field, code_context)
        
        # ── Enrich response body fields ──
        for field in endpoint.response_body:
            _apply_code_context_to_field(field, code_context)
        
        # ── Add state constraints from business rules ──
        for rule in code_context.business_rules:
            # Check if business rule applies to this endpoint
            if _rule_applies_to_endpoint(rule, endpoint):
                constraint = _business_rule_to_constraint(rule)
                if constraint and constraint not in endpoint.state_constraints:
                    endpoint.state_constraints.append(constraint)


def _apply_code_context_to_field(field: FieldSpec, code_context: CodeContext) -> None:
    """
    Apply code-derived constraints to a field spec.
    
    Args:
        field: Field to enhance (modified in-place)
        code_context: Code context with enums and validators
    """
    # ── Apply enum values ──
    # Check if field name matches an enum (e.g., "status" matches "OrderStatus")
    for enum_def in code_context.enums:
        # Match by exact name or by pattern (e.g., status matches OrderStatus)
        if (enum_def.name.lower() == field.name.lower() or
            enum_def.name.lower().endswith(field.name.lower()) or
            field.name.lower() in enum_def.name.lower()):
            
            if not field.enum:  # Don't override if already set
                field.enum = enum_def.values
                logger.info(f"Applied enum {enum_def.name} to field {field.name}: {enum_def.values}")
                break
    
    # ── Apply validators ──
    validators = code_context.get_validators_for_field(field.name)
    for validator in validators:
        if validator.rule_type == "min_length" and field.min_length is None:
            field.min_length = int(validator.constraint) if validator.constraint else None
        elif validator.rule_type == "max_length" and field.max_length is None:
            field.max_length = int(validator.constraint) if validator.constraint else None
        elif validator.rule_type == "pattern" and not field.format:
            # Could store pattern, but for now just note it's validated
            field.description = (field.description or "") + f" (validated: {validator.constraint})"
        elif validator.rule_type == "required":
            field.required = True


def _rule_applies_to_endpoint(rule: BusinessRule, endpoint: Endpoint) -> bool:
    """
    Check if a business rule applies to a specific endpoint.
    
    Args:
        rule: Business rule
        endpoint: Endpoint to check
    
    Returns:
        True if rule applies to this endpoint
    """
    if not rule.applies_to:
        return False
    
    applies_to_lower = rule.applies_to.lower()
    endpoint_name_lower = endpoint.name.lower()
    url_path_lower = endpoint.url_path.lower()
    
    # Match by class/entity name in endpoint path
    # e.g., "Order" rule applies to "/orders" endpoints
    return (
        applies_to_lower in endpoint_name_lower or
        applies_to_lower in url_path_lower or
        applies_to_lower.rstrip('s') in url_path_lower  # "Order" matches "/orders"
    )


def _business_rule_to_constraint(rule: BusinessRule) -> StateConstraint | None:
    """
    Convert a business rule to a state constraint.
    
    Args:
        rule: Business rule from code analysis
    
    Returns:
        StateConstraint or None if conversion not possible
    """
    # Try to extract field and values from condition
    # Pattern: field == 'value' or field in ['value1', 'value2']
    
    # Simple pattern: status == "shipped"
    match = re.match(r"(\w+)\s*==\s*['\"](\w+)['\"]", rule.condition)
    if match:
        field, value = match.groups()
        return StateConstraint(
            field=field,
            allowed_values=[value],
            description=rule.description,
            error_message=rule.error_message or f"Invalid {field}",
            error_code=409
        )
    
    # Pattern: status in ["shipped", "delivered"]
    match = re.match(r"(\w+)\s+in\s+\[(.*?)\]", rule.condition)
    if match:
        field = match.group(1)
        values_str = match.group(2)
        values = [v.strip().strip("'\"") for v in values_str.split(",")]
        return StateConstraint(
            field=field,
            allowed_values=values,
            description=rule.description,
            error_message=rule.error_message or f"Invalid {field}",
            error_code=409
        )
    
    # Pattern: status not in ["shipped", "delivered"] (blocked values)
    match = re.match(r"(\w+)\s+not\s+in\s+\[(.*?)\]", rule.condition)
    if match:
        field = match.group(1)
        values_str = match.group(2)
        blocked_values = [v.strip().strip("'\"") for v in values_str.split(",")]
        return StateConstraint(
            field=field,
            allowed_values=[],
            blocked_values=blocked_values,
            description=rule.description,
            error_message=rule.error_message or f"Invalid {field}",
            error_code=409
        )
    
    # If we can't parse it, return None
    logger.debug(f"Could not convert business rule to constraint: {rule.condition}")
    return None
