"""Test planner for deciding what tests should exist."""
from models.context import SystemContext
from models.test_plan import TestScenario, TestPlan


def plan_tests(context: SystemContext, existing_tests: list[str] = None) -> TestPlan:
    """
    Plan tests based on system context.

    PLANNER RULES:
    For each endpoint:
      1. Generate "positive" test (happy path, 200 OK)
      2. If requires_auth → generate "no_auth" test (expect 401)
      3. If depends_on another endpoint → generate "dependency_failure" test
      4. For GET endpoints with :id → generate "invalid_id" test (404)
    Skip if test_name already in existing_tests (dedup)

    Args:
        context: SystemContext with endpoints and auth rules
        existing_tests: List of test names already implemented (for dedup)

    Returns:
        TestPlan with all scenarios
    """
    if existing_tests is None:
        existing_tests = []

    existing_tests_set = set(existing_tests)
    scenarios = []

    for endpoint in context.endpoints:
        # Generate base test name from endpoint
        base_name = endpoint.name

        # 1. Positive test (happy path)
        positive_test_name = f"{base_name}_positive"
        if positive_test_name not in existing_tests_set:
            scenarios.append(
                TestScenario(
                    test_name=positive_test_name,
                    endpoint=endpoint.name,
                    description=f"Positive test for {endpoint.method} {endpoint.url_path}",
                    test_type="positive",
                )
            )

        # 2. No-auth test (if requires_auth)
        if endpoint.requires_auth:
            no_auth_test_name = f"{base_name}_no_auth"
            if no_auth_test_name not in existing_tests_set:
                scenarios.append(
                    TestScenario(
                        test_name=no_auth_test_name,
                        endpoint=endpoint.name,
                        description=f"No-auth test for {endpoint.method} {endpoint.url_path} (expect 401)",
                        test_type="no_auth",
                    )
                )

        # 3. Dependency failure test (if has dependencies)
        if endpoint.depends_on:
            for dep in endpoint.depends_on:
                dep_fail_test_name = f"{base_name}_dependency_fail_{dep}"
                if dep_fail_test_name not in existing_tests_set:
                    scenarios.append(
                        TestScenario(
                            test_name=dep_fail_test_name,
                            endpoint=endpoint.name,
                            description=f"Dependency failure test: {endpoint.name} depends on {dep}",
                            test_type="dependency_failure",
                        )
                    )

        # 4. Invalid ID test (if path contains :id)
        if ":id" in endpoint.url_path:
            invalid_id_test_name = f"{base_name}_invalid_id"
            if invalid_id_test_name not in existing_tests_set:
                scenarios.append(
                    TestScenario(
                        test_name=invalid_id_test_name,
                        endpoint=endpoint.name,
                        description=f"Invalid ID test for {endpoint.method} {endpoint.url_path}",
                        test_type="invalid_input",
                    )
                )

    # Build rationale
    total_planned = len(scenarios)
    total_existing = len(existing_tests_set)
    rationale = (
        f"Planned {total_planned} tests covering {len(context.endpoints)} endpoints. "
        f"Deduped against {total_existing} existing tests. "
        f"Coverage includes: positive tests, auth failures, dependency checks, invalid input."
    )

    return TestPlan(scenarios=scenarios, rationale=rationale)
