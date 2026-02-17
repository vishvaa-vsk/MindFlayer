"""Type enforcement from schema.

Validates that test payloads match the FieldSpec types declared on endpoints.
Catches common LLM errors:
- String values where integers are expected (e.g., "quantity": "2")
- Missing required fields in positive test payloads
- Invalid format values (e.g., "not-a-uuid" for uuid fields)
- Wrong top-level payload structure

This runs on the abstract model level — all output formats benefit.
"""
from __future__ import annotations

import re
import logging
from models.context import Endpoint, FieldSpec
from validator.models import TypeIssue

logger = logging.getLogger(__name__)

# ── Format validation regexes ─────────────────────────────
_FORMAT_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"),
    "uuid": re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    ),
    "uri": re.compile(r"^https?://"),
    "url": re.compile(r"^https?://"),
    "date-time": re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "phone": re.compile(r"^\+?[\d\s()-]{7,}$"),
}

# Python type mapping from FieldSpec types
_TYPE_MAP: dict[str, set[type]] = {
    "string": {str},
    "integer": {int},
    "number": {int, float},
    "boolean": {bool},
    "array": {list},
    "object": {dict},
}


def enforce_types(
    test_name: str,
    payload: dict | None,
    endpoint: Endpoint | None,
    test_type: str = "positive",
) -> tuple[dict | None, list[TypeIssue]]:
    """Validate and repair payload types against endpoint FieldSpecs.

    Returns:
        (repaired_payload, list_of_issues)
        The repaired payload has coerced types where possible.
    """
    if payload is None or endpoint is None:
        return payload, []

    fields = endpoint.request_body
    if not fields:
        return payload, []

    field_map = {f.name: f for f in fields}
    issues: list[TypeIssue] = []
    repaired = dict(payload)  # Shallow copy

    for field_name, value in payload.items():
        if field_name.startswith("_"):
            continue  # Skip internal hints like _omit_field

        spec = field_map.get(field_name)
        if spec is None:
            continue  # Extra field — may be intentional for test

        # ── Type check ────────────────────────────────────
        expected_types = _TYPE_MAP.get(spec.field_type, {str})
        if type(value) not in expected_types:
            coerced = _try_coerce(value, spec.field_type)
            if coerced is not None:
                repaired[field_name] = coerced
                issues.append(TypeIssue(
                    test_name=test_name,
                    field_name=field_name,
                    expected_type=spec.field_type,
                    actual_type=type(value).__name__,
                    actual_value=str(value)[:50],
                    suggestion=f"Coerced '{value}' → {coerced} ({spec.field_type})",
                ))
            else:
                issues.append(TypeIssue(
                    test_name=test_name,
                    field_name=field_name,
                    expected_type=spec.field_type,
                    actual_type=type(value).__name__,
                    actual_value=str(value)[:50],
                    suggestion=f"Cannot coerce '{value}' to {spec.field_type}",
                ))

        # ── Format check (only for positive tests) ────────
        if test_type == "positive" and spec.format and isinstance(value, str):
            pattern = _FORMAT_PATTERNS.get(spec.format)
            if pattern and not pattern.match(value):
                # Generate a valid value from FieldSpec
                valid_value = spec.example_value()
                repaired[field_name] = valid_value
                issues.append(TypeIssue(
                    test_name=test_name,
                    field_name=field_name,
                    expected_type=f"string({spec.format})",
                    actual_type="string",
                    actual_value=str(value)[:50],
                    suggestion=f"Replaced invalid {spec.format} with '{valid_value}'",
                ))

    # ── Missing required fields check (positive tests only) ──
    if test_type == "positive":
        for field in fields:
            if field.required and field.name not in repaired:
                repaired[field.name] = field.example_value()
                issues.append(TypeIssue(
                    test_name=test_name,
                    field_name=field.name,
                    expected_type=field.field_type,
                    actual_type="<missing>",
                    actual_value="<not present>",
                    suggestion=f"Added missing required field with default: {field.example_value()}",
                ))

    return repaired, issues


def validate_payload_structure(
    test_name: str,
    payload: dict | None,
    endpoint: Endpoint | None,
) -> list[TypeIssue]:
    """Check structural issues without repairing.

    Returns issues only — used for reporting, not mutation.
    """
    if payload is None or endpoint is None:
        return []

    issues: list[TypeIssue] = []
    field_map = {f.name: f for f in endpoint.request_body}

    # Check for unknown fields
    for key in payload:
        if key.startswith("_"):
            continue
        if key not in field_map:
            issues.append(TypeIssue(
                test_name=test_name,
                field_name=key,
                expected_type="<not in schema>",
                actual_type=type(payload[key]).__name__,
                actual_value=str(payload[key])[:50],
                suggestion=f"Field '{key}' not found in endpoint schema — may be ignored by API",
            ))

    return issues


# ── Coercion helpers ──────────────────────────────────────

def _try_coerce(value, target_type: str):
    """Attempt to coerce a value to the target FieldSpec type.

    Returns coerced value or None if impossible.
    """
    try:
        if target_type == "integer":
            if isinstance(value, str) and value.isdigit():
                return int(value)
            if isinstance(value, float) and value == int(value):
                return int(value)
        elif target_type == "number":
            if isinstance(value, str):
                return float(value)
        elif target_type == "boolean":
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    return True
                if value.lower() in ("false", "0", "no"):
                    return False
        elif target_type == "string":
            return str(value)
    except (ValueError, TypeError):
        pass
    return None
