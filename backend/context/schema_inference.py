"""Schema inference engine — infers request/response schemas from endpoint paths and requirements.

Two-tier approach:
  Tier 1: Deterministic domain keyword mapping (no API key needed)
  Tier 2: LLM-based refinement (when API key is available)
"""
import json
import logging
import re

from models.context import Endpoint, FieldSpec, StateConstraint

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Tier 1 — Deterministic Domain Rules
# ═══════════════════════════════════════════════════════════

# Domain patterns: map URL patterns to likely request body fields.
# Each entry: (path_keywords, method_filter, fields)
DOMAIN_SCHEMAS: list[tuple[list[str], list[str] | None, list[dict]]] = [
    # ── Auth / User Registration ──
    (
        ["register", "signup", "sign-up"],
        ["POST"],
        [
            {"name": "email", "field_type": "string", "format": "email", "required": True, "example": "user@example.com"},
            {"name": "password", "field_type": "string", "format": "password", "required": True, "min_length": 8, "example": "SecureP@ss123"},
            {"name": "username", "field_type": "string", "required": False, "min_length": 3, "max_length": 30, "example": "john_doe"},
            {"name": "full_name", "field_type": "string", "required": False, "example": "John Doe"},
        ],
    ),
    (
        ["login", "signin", "sign-in", "auth/token"],
        ["POST"],
        [
            {"name": "email", "field_type": "string", "format": "email", "required": True, "example": "user@example.com"},
            {"name": "password", "field_type": "string", "format": "password", "required": True, "example": "SecureP@ss123"},
        ],
    ),

    # ── Orders / E-commerce ──
    (
        ["orders", "order"],
        ["POST", "PUT"],
        [
            {"name": "product_id", "field_type": "string", "format": "uuid", "required": True, "description": "Product to order"},
            {"name": "quantity", "field_type": "integer", "required": True, "example": "2"},
            {"name": "shipping_address", "field_type": "string", "required": True, "example": "123 Main St, Springfield, IL"},
            {"name": "payment_method", "field_type": "string", "required": False, "enum": ["credit_card", "paypal", "bank_transfer"], "example": "credit_card"},
        ],
    ),

    # ── Products / Catalog ──
    (
        ["products", "product", "items", "item", "catalog"],
        ["POST", "PUT"],
        [
            {"name": "name", "field_type": "string", "required": True, "example": "Wireless Headphones"},
            {"name": "price", "field_type": "number", "required": True, "example": "79.99"},
            {"name": "description", "field_type": "string", "required": False, "example": "Noise-cancelling over-ear headphones"},
            {"name": "category", "field_type": "string", "required": False, "example": "electronics"},
            {"name": "sku", "field_type": "string", "required": False, "example": "WH-1000XM5"},
        ],
    ),

    # ── Users / Profiles ──
    (
        ["users", "user", "profile", "profiles", "account"],
        ["POST", "PUT", "PATCH"],
        [
            {"name": "name", "field_type": "string", "required": True, "example": "Jane Smith"},
            {"name": "email", "field_type": "string", "format": "email", "required": True, "example": "jane@example.com"},
            {"name": "phone", "field_type": "string", "format": "phone", "required": False, "example": "+1-555-0199"},
            {"name": "role", "field_type": "string", "required": False, "enum": ["user", "admin", "moderator"], "example": "user"},
        ],
    ),

    # ── Comments / Reviews ──
    (
        ["comments", "comment", "reviews", "review", "feedback"],
        ["POST"],
        [
            {"name": "content", "field_type": "string", "required": True, "min_length": 1, "max_length": 2000, "example": "Great product, highly recommended!"},
            {"name": "rating", "field_type": "integer", "required": False, "example": "5", "description": "Rating from 1-5"},
        ],
    ),

    # ── Posts / Articles / Blog ──
    (
        ["posts", "post", "articles", "article", "blog"],
        ["POST", "PUT"],
        [
            {"name": "title", "field_type": "string", "required": True, "min_length": 1, "max_length": 200, "example": "Getting Started with API Testing"},
            {"name": "body", "field_type": "string", "required": True, "example": "In this guide we explore..."},
            {"name": "tags", "field_type": "array", "required": False, "example": '["testing", "api"]'},
            {"name": "published", "field_type": "boolean", "required": False, "example": "false"},
        ],
    ),

    # ── Payments / Transactions ──
    (
        ["payments", "payment", "transactions", "transaction", "charges", "charge"],
        ["POST"],
        [
            {"name": "amount", "field_type": "number", "required": True, "example": "99.99"},
            {"name": "currency", "field_type": "string", "required": True, "enum": ["USD", "EUR", "GBP", "INR"], "example": "USD"},
            {"name": "payment_method", "field_type": "string", "required": True, "enum": ["credit_card", "paypal", "bank_transfer"], "example": "credit_card"},
            {"name": "description", "field_type": "string", "required": False, "example": "Order #1234 payment"},
        ],
    ),

    # ── Notifications ──
    (
        ["notifications", "notification", "alerts", "messages"],
        ["POST"],
        [
            {"name": "recipient_id", "field_type": "string", "format": "uuid", "required": True},
            {"name": "title", "field_type": "string", "required": True, "example": "New order received"},
            {"name": "message", "field_type": "string", "required": True, "example": "You have a new order #1234"},
            {"name": "channel", "field_type": "string", "required": False, "enum": ["email", "sms", "push"], "example": "email"},
        ],
    ),
]

# State constraint patterns detected from requirements text.
STATE_PATTERNS = [
    # "can only be cancelled if status is Pending"
    (
        r"(?:can\s+only\s+be\s+)?(\w+(?:ed|led)?)\s+(?:if|when)\s+(?:the\s+)?status\s+(?:is|=|==)\s+['\"]?(\w+)['\"]?",
        lambda m: {"field": "status", "allowed_values": [m.group(2).lower()]},
    ),
    # "cannot cancel if Shipped"
    (
        r"cannot\s+(\w+)\s+(?:if|when)\s+(?:the\s+)?(?:status\s+(?:is|=)\s+)?['\"]?(\w+)['\"]?",
        lambda m: {"field": "status", "blocked_values": [m.group(2).lower()]},
    ),
    # "Orders can only be cancelled if status is Pending. Cannot cancel if Shipped."
    # Handled by combining the above two patterns.
]

# Role patterns detected from requirements text.
ROLE_PATTERNS = [
    r"(\w+)\s+(?:users?\s+)?can\s+(?:only\s+)?(\w+)",  # "Admin users can delete"
    r"(?:requires?\s+)(\w+)_auth",                        # "requires admin_auth"
    r"(\w+)\s+role\s+(?:is\s+)?required",                 # "admin role is required"
]


def infer_schemas(endpoints: list[Endpoint], requirements_text: str = "") -> None:
    """Infer and populate request/response schemas on endpoints in-place.

    Tier 1: Deterministic domain keyword matching (always runs).
    Tier 2: LLM refinement (when API key is available).

    Args:
        endpoints: List of endpoints to enrich (modified in-place).
        requirements_text: Original requirements for constraint extraction.
    """
    for ep in endpoints:
        # Skip GET/DELETE — typically no request body
        if ep.method in ("GET", "HEAD", "OPTIONS"):
            # Still set response body for GETs
            if not ep.response_body:
                ep.response_body = _infer_response_fields(ep)
            continue

        if not ep.request_body:
            ep.request_body = _infer_request_fields(ep)
        if not ep.response_body:
            ep.response_body = _infer_response_fields(ep)

    # Extract state constraints from requirements text
    if requirements_text:
        _extract_state_constraints(endpoints, requirements_text)
        _extract_roles(endpoints, requirements_text)

    # Tier 2: LLM refinement (optional, best-effort)
    _try_llm_refinement(endpoints, requirements_text)


def _infer_request_fields(ep: Endpoint) -> list[FieldSpec]:
    """Tier 1: Match endpoint path against domain schemas."""
    path_parts = ep.url_path.lower().strip("/").split("/")
    path_str = "/".join(path_parts)

    # Try each domain schema
    for keywords, methods, fields in DOMAIN_SCHEMAS:
        if methods and ep.method not in methods:
            continue
        if any(kw in path_str for kw in keywords):
            return [FieldSpec(**f) for f in fields]

    # Generic fallback — resource-aware, NOT {resource}_name
    return _generic_request_fields(ep)


def _infer_response_fields(ep: Endpoint) -> list[FieldSpec]:
    """Infer typical response fields."""
    resource = _extract_resource(ep.url_path)
    fields = [
        FieldSpec(name="id", field_type="string", format="uuid",
                  example="550e8400-e29b-41d4-a716-446655440000"),
    ]
    # Add request body fields to response (common REST pattern)
    if ep.request_body:
        fields.extend(ep.request_body)
    # Always add timestamps
    fields.append(FieldSpec(name="created_at", field_type="string",
                            format="date-time", required=False,
                            example="2025-06-15T10:30:00Z"))
    fields.append(FieldSpec(name="updated_at", field_type="string",
                            format="date-time", required=False,
                            example="2025-06-15T10:30:00Z"))
    return fields


def _generic_request_fields(ep: Endpoint) -> list[FieldSpec]:
    """Fallback: generate resource-aware fields instead of templated ones."""
    resource = _extract_resource(ep.url_path)

    # Use resource name to create sensible fields
    return [
        FieldSpec(name="name", field_type="string", required=True,
                  example=f"Test {resource.title()}"),
        FieldSpec(name="description", field_type="string", required=False,
                  example=f"Description for {resource}"),
    ]


def _extract_resource(url_path: str) -> str:
    """Extract resource name from URL path: /orders/:id → order."""
    parts = url_path.strip("/").split("/")
    # Skip path params
    resource_parts = [p for p in parts if not p.startswith(":") and not p.startswith("{")]
    resource = resource_parts[0] if resource_parts else "resource"
    # Singularize
    if resource.endswith("ies"):
        return resource[:-3] + "y"
    if resource.endswith("s") and len(resource) > 1:
        return resource[:-1]
    return resource


def _extract_state_constraints(endpoints: list[Endpoint], text: str) -> None:
    """Extract state constraints from requirements text."""
    text_lower = text.lower()

    for pattern, extractor in STATE_PATTERNS:
        for match in re.finditer(pattern, text_lower, re.IGNORECASE):
            constraint_data = extractor(match)
            constraint = StateConstraint(
                field=constraint_data.get("field", "status"),
                allowed_values=constraint_data.get("allowed_values", []),
                blocked_values=constraint_data.get("blocked_values", []),
                description=match.group(0).strip(),
                error_code=409,
            )

            # Find the relevant endpoint (look for the action verb in endpoint names/paths)
            action = match.group(1).lower()
            for ep in endpoints:
                ep_keywords = ep.name.lower() + " " + ep.url_path.lower()
                if action in ep_keywords or _action_matches_endpoint(action, ep):
                    if constraint not in ep.state_constraints:
                        ep.state_constraints.append(constraint)
                    break


def _action_matches_endpoint(action: str, ep: Endpoint) -> bool:
    """Check if an action verb matches an endpoint (e.g., 'cancelled' matches DELETE /orders/:id/cancel)."""
    # Strip common suffixes: cancelled→cancel, deleted→delete, updated→update
    stem = re.sub(r"(ed|led|d)$", "", action)
    return stem in ep.url_path.lower() or stem in ep.name.lower()


def _extract_roles(endpoints: list[Endpoint], text: str) -> None:
    """Extract role requirements from requirements text."""
    text_lower = text.lower()

    # Look for role mentions like "admin can delete", "user can create"
    role_mentions: dict[str, list[str]] = {}  # role → [action_verbs]

    for pattern in ROLE_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            role = match.group(1).lower()
            if role in ("user", "admin", "moderator", "manager", "editor", "viewer", "owner"):
                if role not in role_mentions:
                    role_mentions[role] = []
                if match.lastindex and match.lastindex >= 2:
                    role_mentions[role].append(match.group(2).lower())

    # Assign roles to endpoints
    if role_mentions:
        roles_list = list(role_mentions.keys())
        for ep in endpoints:
            if ep.requires_auth:
                # Check if any role action matches this endpoint
                matched_roles = set()
                for role, actions in role_mentions.items():
                    for action in actions:
                        stem = re.sub(r"(e?s|ed|ing)$", "", action)
                        method_map = {"get": "GET", "creat": "POST", "updat": "PUT",
                                      "delet": "DELETE", "remov": "DELETE", "cancel": "DELETE"}
                        if stem in ep.name.lower() or stem in ep.url_path.lower():
                            matched_roles.add(role)
                        elif stem in method_map and method_map[stem] == ep.method:
                            matched_roles.add(role)

                if matched_roles:
                    ep.roles = list(matched_roles)
                elif not ep.roles:
                    # Default: all mentioned roles can access auth-required endpoints
                    ep.roles = roles_list


def _try_llm_refinement(endpoints: list[Endpoint], requirements_text: str) -> None:
    """Tier 2: Use LLM to refine inferred schemas (best-effort, non-blocking)."""
    if not requirements_text:
        return

    try:
        from config import get_settings
        settings = get_settings()

        # Only attempt LLM refinement if we have an API key
        if not settings.has_api_key and settings.llm_provider in ("openrouter", "azure"):
            return

        from adapters.registry import get_adapter
        adapter = get_adapter()

        # Build a summary of what we've inferred
        endpoint_summary = []
        for ep in endpoints:
            fields_str = ", ".join(f.name for f in ep.request_body)
            endpoint_summary.append(
                f"  {ep.method} {ep.url_path}: request fields=[{fields_str}]"
            )
        endpoints_block = "\n".join(endpoint_summary)

        prompt = f"""Review these API endpoints and their inferred request fields. Based on the original requirements, suggest corrections.

Original requirements:
{requirements_text}

Current inference:
{endpoints_block}

Return a JSON object with corrections. Only include endpoints that need changes.
Format:
{{
  "corrections": [
    {{
      "endpoint": "POST /path",
      "add_fields": [{{"name": "field_name", "field_type": "string", "format": "email", "required": true}}],
      "remove_fields": ["wrong_field"],
      "state_constraints": [{{"field": "status", "allowed_values": ["pending"], "description": "rule"}}]
    }}
  ]
}}

If no corrections needed, return: {{"corrections": []}}
Only return valid JSON, no explanations."""

        messages = [
            {"role": "system", "content": "You are an API schema expert. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        result = adapter.chat(
            messages=messages,
            model=settings.parsing_model,
            temperature=0.2,
            max_tokens=800,
        )

        # Strip markdown fences
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        corrections = json.loads(result)
        _apply_corrections(endpoints, corrections.get("corrections", []))
        logger.info(f"LLM schema refinement applied {len(corrections.get('corrections', []))} corrections")

    except Exception as e:
        # LLM refinement is best-effort — log and continue
        logger.debug(f"LLM schema refinement skipped: {e}")


def _apply_corrections(endpoints: list[Endpoint], corrections: list[dict]) -> None:
    """Apply LLM corrections to endpoints."""
    for correction in corrections:
        target = correction.get("endpoint", "")
        parts = target.split(" ", 1)
        if len(parts) != 2:
            continue
        method, path = parts[0].upper(), parts[1]

        for ep in endpoints:
            if ep.method == method and ep.url_path == path:
                # Remove fields
                remove_names = set(correction.get("remove_fields", []))
                if remove_names:
                    ep.request_body = [f for f in ep.request_body if f.name not in remove_names]

                # Add fields
                for field_data in correction.get("add_fields", []):
                    if not any(f.name == field_data.get("name") for f in ep.request_body):
                        ep.request_body.append(FieldSpec(**field_data))

                # Add state constraints
                for sc_data in correction.get("state_constraints", []):
                    constraint = StateConstraint(
                        field=sc_data.get("field", "status"),
                        allowed_values=sc_data.get("allowed_values", []),
                        blocked_values=sc_data.get("blocked_values", []),
                        description=sc_data.get("description", ""),
                    )
                    if constraint not in ep.state_constraints:
                        ep.state_constraints.append(constraint)
                break


def fields_to_payload(fields: list[FieldSpec]) -> dict:
    """Convert a list of FieldSpecs into a realistic test payload dict.

    Useful for generators that need an example payload (Postman, pytest templates).
    """
    payload = {}
    for f in fields:
        if not f.required and f.name in ("updated_at", "created_at"):
            continue  # Skip metadata-only fields
        payload[f.name] = f.example_value()
    return payload
