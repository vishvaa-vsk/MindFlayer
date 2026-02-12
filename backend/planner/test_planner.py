"""Test planner for deciding what tests should exist.

Intelligent planning using enriched endpoint metadata:
- FieldSpec → field_validation, boundary_value tests
- StateConstraint → state_conflict tests
- Roles → forbidden_role tests
- Dependencies → dependency_failure tests
"""
from models.context import SystemContext
from models.test_plan import TestScenario, TestPlan


def plan_tests(context: SystemContext, existing_tests: list[str] = None) -> TestPlan:
    """
    Plan tests based on system context with intelligent scenario generation.

    PLANNER RULES:
    For each endpoint:
      1. positive              — happy path (200/201/204)
      2. no_auth               — if requires_auth (expect 401)
      3. dependency_failure    — if depends_on (expect 400/404)
      4. invalid_input         — if path has :id (expect 404)
      5. state_conflict        — if state_constraints (expect 409)
      6. forbidden_role        — if multiple roles exist (expect 403)
      7. field_validation      — if FieldSpec has format/required (expect 422)
      8. boundary_value        — if FieldSpec has min/max_length (expect 422)

    Skip if test_name already in existing_tests (dedup).

    Args:
        context: SystemContext with enriched endpoints
        existing_tests: List of test names already implemented (for dedup)

    Returns:
        TestPlan with all scenarios
    """
    if existing_tests is None:
        existing_tests = []

    existing_tests_set = set(existing_tests)
    scenarios = []

    def _add(name: str, endpoint: str, description: str, test_type: str,
             expected_status: int = 200, payload_hint: dict | None = None):
        """Add scenario if not already existing."""
        if name not in existing_tests_set:
            scenarios.append(TestScenario(
                test_name=name,
                endpoint=endpoint,
                description=description,
                test_type=test_type,
                expected_status=expected_status,
                payload_hint=payload_hint,
            ))

    for endpoint in context.endpoints:
        base_name = endpoint.name
        method = endpoint.method
        path = endpoint.url_path

        # ── 1. Positive test (happy path) ──
        _add(
            name=f"{base_name}_positive",
            endpoint=endpoint.name,
            description=f"Verify {method} {path} returns success with valid data",
            test_type="positive",
            expected_status=endpoint.expected_success_code,
        )

        # ── 2. No-auth test ──
        if endpoint.requires_auth:
            _add(
                name=f"{base_name}_no_auth",
                endpoint=endpoint.name,
                description=f"Verify {method} {path} rejects unauthenticated requests",
                test_type="no_auth",
                expected_status=401,
            )

        # ── 3. Dependency failure test ──
        if endpoint.depends_on:
            for dep in endpoint.depends_on:
                # 404: resource from dependency doesn't exist because setup was skipped
                _add(
                    name=f"{base_name}_dependency_fail_{dep}",
                    endpoint=endpoint.name,
                    description=f"Verify {endpoint.name} returns 404 when dependency '{dep}' resource does not exist",
                    test_type="dependency_failure",
                    expected_status=404,
                )

        # ── 4. Invalid ID test ──
        if ":id" in endpoint.url_path:
            _add(
                name=f"{base_name}_invalid_id",
                endpoint=endpoint.name,
                description=f"Verify {method} {path} returns 404 for non-existent resource",
                test_type="invalid_input",
                expected_status=404,
            )

        # ── 5. State conflict tests ──
        for constraint in endpoint.state_constraints:
            blocked = constraint.blocked_values or []
            if constraint.allowed_values:
                # Generate test: try the action when NOT in allowed state
                conflict_state = blocked[0] if blocked else "completed"
                _add(
                    name=f"{base_name}_state_conflict_{constraint.field}",
                    endpoint=endpoint.name,
                    description=(
                        f"Verify {method} {path} returns {constraint.error_code} "
                        f"when {constraint.field} is '{conflict_state}' "
                        f"(only allowed when {constraint.field} in {constraint.allowed_values})"
                    ),
                    test_type="state_conflict",
                    expected_status=constraint.error_code,
                    payload_hint={constraint.field: conflict_state},
                )
            for blocked_val in blocked:
                _add(
                    name=f"{base_name}_state_blocked_{blocked_val}",
                    endpoint=endpoint.name,
                    description=(
                        f"Verify {method} {path} returns {constraint.error_code} "
                        f"when {constraint.field} is '{blocked_val}'"
                    ),
                    test_type="state_conflict",
                    expected_status=constraint.error_code,
                    payload_hint={constraint.field: blocked_val},
                )

        # ── 6. Forbidden role tests ──
        if len(endpoint.roles) > 0 and endpoint.requires_auth:
            # Find roles that exist in the system but aren't assigned to this endpoint
            all_roles = set()
            for ep in context.endpoints:
                all_roles.update(ep.roles)
            forbidden_roles = all_roles - set(endpoint.roles)
            for role in sorted(forbidden_roles)[:2]:  # Limit to 2 forbidden role tests
                _add(
                    name=f"{base_name}_forbidden_{role}",
                    endpoint=endpoint.name,
                    description=(
                        f"Verify {method} {path} returns 403 for '{role}' role "
                        f"(requires: {', '.join(endpoint.roles)})"
                    ),
                    test_type="forbidden_role",
                    expected_status=403,
                )

        # ── 7. Field validation tests ──
        format_fields = [f for f in endpoint.request_body if f.format in ("email", "phone", "uri", "url", "uuid")]
        for field in format_fields[:2]:  # Limit to 2 format validation tests
            _add(
                name=f"{base_name}_invalid_{field.name}",
                endpoint=endpoint.name,
                description=(
                    f"Verify {method} {path} returns 422 when '{field.name}' "
                    f"has invalid {field.format} format"
                ),
                test_type="field_validation",
                expected_status=422,
                payload_hint={field.name: "not-a-valid-" + (field.format or "value")},
            )

        required_fields = [f for f in endpoint.request_body if f.required]
        if required_fields:
            # Pick the most important required field
            key_field = required_fields[0]
            _add(
                name=f"{base_name}_missing_{key_field.name}",
                endpoint=endpoint.name,
                description=(
                    f"Verify {method} {path} returns 422 when required field "
                    f"'{key_field.name}' is missing"
                ),
                test_type="field_validation",
                expected_status=422,
                payload_hint={"_omit_field": key_field.name},
            )

        # ── 8. Boundary value tests (string length) ──
        boundary_fields = [f for f in endpoint.request_body
                           if f.min_length is not None or f.max_length is not None]
        for field in boundary_fields[:2]:  # Limit to 2 boundary tests
            if field.min_length is not None and field.min_length > 0:
                short_value = "x" * max(1, field.min_length - 1)
                _add(
                    name=f"{base_name}_short_{field.name}",
                    endpoint=endpoint.name,
                    description=(
                        f"Verify {method} {path} returns 422 when '{field.name}' "
                        f"is shorter than {field.min_length} characters"
                    ),
                    test_type="boundary_value",
                    expected_status=422,
                    payload_hint={field.name: short_value},
                )

        # ── 9. Numeric boundary tests (domain reasoning) ──
        numeric_fields = [f for f in endpoint.request_body
                          if f.minimum is not None or f.maximum is not None]
        for field in numeric_fields[:2]:  # Limit to 2 numeric tests
            if field.minimum is not None:
                below_min = field.minimum - 1
                _add(
                    name=f"{base_name}_negative_{field.name}",
                    endpoint=endpoint.name,
                    description=(
                        f"Verify {method} {path} returns 422 when '{field.name}' "
                        f"is {below_min} (below minimum {field.minimum})"
                    ),
                    test_type="numeric_boundary",
                    expected_status=422,
                    payload_hint={field.name: below_min},
                )
                # Zero boundary test when minimum > 0
                if field.minimum > 0:
                    _add(
                        name=f"{base_name}_zero_{field.name}",
                        endpoint=endpoint.name,
                        description=(
                            f"Verify {method} {path} returns 422 when '{field.name}' "
                            f"is 0 (minimum is {field.minimum})"
                        ),
                        test_type="numeric_boundary",
                        expected_status=422,
                        payload_hint={field.name: 0},
                    )

    # Build rationale
    type_counts = {}
    for s in scenarios:
        type_counts[s.test_type] = type_counts.get(s.test_type, 0) + 1

    type_summary = ", ".join(f"{count} {t}" for t, count in sorted(type_counts.items()))
    rationale = (
        f"Planned {len(scenarios)} tests covering {len(context.endpoints)} endpoints. "
        f"Deduped against {len(existing_tests_set)} existing tests. "
        f"Breakdown: {type_summary}."
    )

    return TestPlan(scenarios=scenarios, rationale=rationale)
