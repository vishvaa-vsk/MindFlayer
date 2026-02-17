"""Pytest code generator with domain-aware payloads and advanced test types.

Supports both raw TestPlan and ValidatedTestPlan input.
When ValidatedTestPlan is provided, uses preconditions, variable refs,
and type-checked payloads for higher-quality output.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from models.test_plan import TestPlan
from models.context import SystemContext
from context.llm_parser import generate_tests_batch_with_llm
from context.schema_inference import fields_to_payload
from validator.models import ValidatedTestPlan, ValidatedScenario, Precondition
from validator.pipeline import validate_plan, validate_output

logger = logging.getLogger(__name__)

# ── Batch / Parallelism Config ────────────────────────────
BATCH_SIZE = 10          # scenarios per LLM call
MAX_WORKERS = 3          # parallel LLM calls


def generate_pytest(test_plan: TestPlan, context: SystemContext | None = None) -> str:
    """
    Generate pytest code from a test plan.

    Supports two paths:
    1. Raw TestPlan → auto-validates via pipeline → validated generation
    2. Pre-validated ValidatedTestPlan → direct validated generation

    Both paths use batched LLM calls with template fallback,
    and post-generation AST checking + auto-repair.

    Args:
        test_plan: TestPlan or ValidatedTestPlan with scenarios to generate
        context: Optional SystemContext for endpoint metadata

    Returns:
        Complete, runnable, syntax-validated pytest code as string
    """
    # Build endpoint lookup from context
    endpoint_lookup = {}
    if context:
        for ep in context.endpoints:
            endpoint_lookup[ep.name] = ep

    # ── Auto-validate if raw TestPlan ─────────────────────
    validated: ValidatedTestPlan | None = None
    if isinstance(test_plan, ValidatedTestPlan):
        validated = test_plan
    elif context:
        try:
            validated = validate_plan(test_plan, context)
            logger.info("[pytest_gen] Auto-validated plan: %d scenarios, %d preconditions injected",
                        len(validated.scenarios), validated.report.injected_preconditions)
        except Exception as e:
            logger.warning("[pytest_gen] Validation failed, falling back to raw plan: %s", str(e)[:100])

    # ── Emit fixtures ─────────────────────────────────────
    code_lines = _emit_header_and_fixtures(validated)

    # ── Batch LLM generation (fast path) ──────────────────
    llm_results = _batch_generate_with_llm(test_plan, endpoint_lookup)

    # ── Assemble tests ────────────────────────────────────
    scenarios_to_emit = validated.scenarios if validated else test_plan.scenarios
    for scenario in scenarios_to_emit:
        if isinstance(scenario, ValidatedScenario):
            vs = scenario
            test_name = vs.test_name
            endpoint_name = vs.endpoint
            test_type = vs.test_type
            description = vs.description
        else:
            vs = None
            test_name = scenario.test_name
            endpoint_name = scenario.endpoint
            test_type = scenario.test_type
            description = scenario.description

        ep = endpoint_lookup.get(endpoint_name)
        method = ep.method if ep else "GET"
        path = ep.url_path if ep else "/"
        requires_auth = ep.requires_auth if ep else False

        if test_name in llm_results:
            # LLM-generated code — validate inline
            llm_code = llm_results[test_name]
            code_lines.append(llm_code)
        elif vs and vs.preconditions:
            # Validated scenario with preconditions — use enriched template
            code_lines.append(_generate_validated_test(
                scenario=vs,
                method=method,
                path=path,
                requires_auth=requires_auth,
                endpoint=ep,
            ))
        else:
            # Template fallback — instant, no LLM call
            code_lines.append(_generate_template_test(
                test_name=test_name,
                method=method,
                path=path,
                test_type=test_type,
                description=description,
                requires_auth=requires_auth,
                endpoint=ep,
                scenario=scenario,
            ))

        code_lines.append("")
        code_lines.append("")

    # Test suite summary
    llm_count = sum(1 for s in (validated.scenarios if validated else test_plan.scenarios)
                    if s.test_name in llm_results)
    total = len(validated.scenarios) if validated else len(test_plan.scenarios)
    tmpl_count = total - llm_count
    rationale = validated.rationale if validated else test_plan.rationale
    code_lines.extend([
        "# ── Summary ──────────────────────────────────────────────",
        f"# Total tests: {total}",
        f"# LLM-generated: {llm_count}, Template-generated: {tmpl_count}",
        f"# Coverage: {rationale}",
    ])
    if validated:
        rpt = validated.report
        code_lines.append(
            f"# Validation: {rpt.injected_preconditions} preconditions, "
            f"{len(rpt.type_mismatches)} type fixes, {rpt.reordered_count} reordered"
        )
    code_lines.append("# Generated by MindFlayer — AI-powered test intelligence")

    raw_code = "\n".join(code_lines)

    # ── Post-generation AST check + repair ────────────────
    final_code, remaining_issues, repairs = validate_output(raw_code, "pytest", auto_repair=True)
    if repairs:
        logger.info("[pytest_gen] Applied %d post-generation repair(s): %s",
                     len(repairs), "; ".join(repairs[:3]))
    if remaining_issues:
        logger.warning("[pytest_gen] %d syntax issue(s) remain after repair", len(remaining_issues))

    return final_code


def _batch_generate_with_llm(test_plan: TestPlan, endpoint_lookup: dict) -> dict[str, str]:
    """
    Generate test code via batched, parallel LLM calls.

    Batches scenarios (BATCH_SIZE per call) and runs batches in parallel
    (MAX_WORKERS threads). Returns a dict mapping test_name → code.
    """
    # Prepare scenario dicts for batch API
    all_scenarios = []
    for scenario in test_plan.scenarios:
        ep = endpoint_lookup.get(scenario.endpoint)
        all_scenarios.append({
            "test_name": scenario.test_name,
            "endpoint_method": ep.method if ep else "GET",
            "endpoint_path": ep.url_path if ep else "/",
            "test_type": scenario.test_type,
            "description": scenario.description,
            "requires_auth": ep.requires_auth if ep else False,
            "depends_on": ep.depends_on if ep else [],
        })

    if not all_scenarios:
        return {}

    # Split into batches
    batches = [
        all_scenarios[i:i + BATCH_SIZE]
        for i in range(0, len(all_scenarios), BATCH_SIZE)
    ]

    logger.info(
        "[pytest_gen] Generating %d tests in %d batch(es) with %d parallel worker(s)",
        len(all_scenarios), len(batches), min(MAX_WORKERS, len(batches)),
    )

    merged_results: dict[str, str] = {}

    # Run batches in parallel
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
        futures = {
            pool.submit(generate_tests_batch_with_llm, batch): idx
            for idx, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                batch_result = future.result()
                merged_results.update(batch_result)
                logger.info(
                    "[pytest_gen] Batch %d returned %d test(s)",
                    batch_idx + 1, len(batch_result),
                )
            except Exception as e:
                logger.warning(
                    "[pytest_gen] Batch %d failed: %s", batch_idx + 1, str(e)[:100],
                )

    logger.info(
        "[pytest_gen] LLM generated %d/%d tests, %d will use template fallback",
        len(merged_results), len(all_scenarios),
        len(all_scenarios) - len(merged_results),
    )
    return merged_results


def _emit_header_and_fixtures(validated: ValidatedTestPlan | None) -> list[str]:
    """Emit module header, imports, and fixtures.

    When validated plan is available, generates a resource_factory fixture
    that handles precondition setup.
    """
    lines = [
        '"""Auto-generated test suite by MindFlayer."""',
        "import pytest",
        "import json",
        "",
        "",
        "# ── Fixtures ──────────────────────────────────────────────",
        "",
        "@pytest.fixture",
        "def client():",
        '    """Provide test client fixture."""',
        "    from fastapi.testclient import TestClient",
        "    from main import app",
        "    return TestClient(app)",
        "",
        "",
        "@pytest.fixture",
        "def auth_headers():",
        '    """Provide authenticated headers."""',
        '    return {"Authorization": "Bearer test-token-valid"}',
        "",
        "",
        "@pytest.fixture",
        "def forbidden_headers():",
        '    """Provide headers for an unauthorized role."""',
        '    return {"Authorization": "Bearer forbidden-role-token"}',
        "",
        "",
    ]

    # ── Resource factory fixture (from validation layer) ──
    if validated and any(s.preconditions for s in validated.scenarios):
        lines.extend([
            "@pytest.fixture",
            "def resource_factory(client, auth_headers):",
            '    """Create resources needed by tests and return captured values.',
            "",
            '    Usage: ids = resource_factory("post__purchase_orders")',
            '    Returns dict with extracted fields (e.g. {"id": "abc-123"})',
            '    """',
            "    created = {}",
            "",
            "    def _create(endpoint_name, method, path, payload=None, extract_field=None):",
            "        cache_key = f'{endpoint_name}_{json.dumps(payload, sort_keys=True)}'",
            "        if cache_key in created:",
            "            return created[cache_key]",
            "        call = getattr(client, method.lower())",
            "        if payload:",
            "            resp = call(path, json=payload, headers=auth_headers)",
            "        else:",
            "            resp = call(path, headers=auth_headers)",
            "        assert resp.status_code in [200, 201, 204], (",
            '            f"Setup failed: {method} {path} returned {resp.status_code}: {resp.text}"',
            "        )",
            "        result = {}",
            "        if resp.status_code != 204:",
            "            try:",
            "                data = resp.json()",
            "                if extract_field and extract_field in data:",
            "                    result[extract_field] = data[extract_field]",
            "                result['_response'] = data",
            "            except Exception:",
            "                pass",
            "        created[cache_key] = result",
            "        return result",
            "",
            "    return _create",
            "",
            "",
        ])

    lines.extend([
        "# ── Tests ────────────────────────────────────────────────",
        "",
    ])
    return lines


def _generate_validated_test(
    scenario: ValidatedScenario,
    method: str,
    path: str,
    requires_auth: bool = False,
    endpoint=None,
) -> str:
    """Generate a test with proper precondition setup from the validation layer.

    This produces tests that:
    - Create required resources before testing
    - Capture IDs from creation responses
    - Use captured IDs in URL paths and payloads
    - Have proper setup/teardown chains
    """
    test_type = scenario.test_type
    lines = []

    # ── Determine fixtures ────────────────────────────────
    fixtures = ["client"]
    if requires_auth and test_type not in ("no_auth",):
        fixtures.append("auth_headers")
    if test_type == "forbidden_role":
        fixtures.append("forbidden_headers")
    if scenario.preconditions:
        fixtures.append("resource_factory")

    fixture_str = ", ".join(fixtures)
    lines.append(f"def test_{scenario.test_name}({fixture_str}):")
    lines.append(f'    """{scenario.description}"""')

    # ── Emit precondition setup ───────────────────────────
    captured_vars: dict[str, str] = {}  # variable_name → python expression
    for i, pre in enumerate(scenario.preconditions):
        lines.append(f"    # Setup: {pre.description}")
        payload_str = json.dumps(pre.payload, indent=8) if pre.payload else "None"
        var_name = f"setup_{i}"
        lines.append(
            f"    {var_name} = resource_factory("
            f'"{pre.endpoint_name}", "{pre.method}", "{pre.path}", '
            f"payload={payload_str}, "
            f'extract_field="{pre.extract_field or ""}"'
            f")"
        )
        if pre.variable_name and pre.extract_field:
            lines.append(
                f'    {pre.variable_name} = {var_name}["{pre.extract_field}"]'
            )
            captured_vars[pre.variable_name] = pre.variable_name

    # ── Resolve :id in path ───────────────────────────────
    test_path = path
    if ":id" in test_path and scenario.variable_refs.get(":id"):
        var_name = scenario.variable_refs[":id"]
        if var_name in captured_vars:
            test_path = path.replace(":id", f"{{{var_name}}}")
            # Use f-string for the path
        else:
            test_path = path.replace(":id", "test-id-123")
    else:
        test_path = path.replace(":id", "test-id-123")

    use_fstring = "{" in test_path
    path_expr = f'f"{test_path}"' if use_fstring else f'"{test_path}"'

    # ── Emit test body ────────────────────────────────────
    if test_type == "positive":
        _emit_positive_body(lines, method, path_expr, requires_auth, endpoint, scenario)
    elif test_type == "no_auth":
        _emit_no_auth_body(lines, method, path_expr, endpoint, scenario)
    elif test_type == "dependency_failure":
        _emit_dependency_failure_body(lines, method, path, requires_auth, endpoint, scenario)
    elif test_type == "invalid_input":
        invalid_path = path.replace(":id", "nonexistent-id-999")
        _emit_invalid_input_body(lines, method, f'"{invalid_path}"', requires_auth)
    elif test_type == "state_conflict":
        _emit_state_conflict_body(lines, method, path_expr, requires_auth, endpoint, scenario)
    elif test_type == "forbidden_role":
        _emit_forbidden_role_body(lines, method, path_expr, endpoint, scenario)
    elif test_type == "field_validation":
        _emit_field_validation_body(lines, method, path_expr, requires_auth, endpoint, scenario)
    elif test_type == "boundary_value":
        _emit_boundary_body(lines, method, path_expr, requires_auth, endpoint, scenario)

    return "\n".join(lines)


def _emit_positive_body(lines, method, path_expr, requires_auth, endpoint, scenario):
    """Emit positive test body with assertions."""
    expected = scenario.expected_status
    if method in ("POST", "PUT", "PATCH"):
        payload = scenario.payload or {}
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload)")
        lines.append(f"    assert response.status_code in [200, 201], f\"Expected 2xx, got {{response.status_code}}: {{response.text[:200]}}\"")
        lines.append(f"    data = response.json()")
        lines.append(f"    assert data is not None")
        if endpoint and endpoint.request_body:
            key_field = endpoint.request_body[0]
            lines.append(f'    assert "{key_field.name}" in data or "id" in data')
    elif method == "DELETE":
        if requires_auth:
            lines.append(f"    response = client.delete({path_expr}, headers=auth_headers)")
        else:
            lines.append(f"    response = client.delete({path_expr})")
        lines.append(f"    assert response.status_code in [200, 204]")
    else:
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}({path_expr}, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}({path_expr})")
        lines.append(f"    assert response.status_code == {expected}, f\"Expected {expected}, got {{response.status_code}}\"")
        lines.append(f"    data = response.json()")
        lines.append(f"    assert data is not None")


def _emit_no_auth_body(lines, method, path_expr, endpoint, scenario):
    """Emit no-auth test body."""
    if method in ("POST", "PUT", "PATCH"):
        payload = scenario.payload or {}
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload)")
    else:
        lines.append(f"    response = client.{method.lower()}({path_expr})")
    lines.append(f"    assert response.status_code in [401, 403]")


def _emit_dependency_failure_body(lines, method, path, requires_auth, endpoint, scenario):
    """Emit dependency failure test — deliberately no setup."""
    invalid_path = path.replace(":id", "test-id-no-setup")
    lines.append(f'    # Dependency failure: skip required setup, verify error handling')
    if method in ("POST", "PUT", "PATCH"):
        payload = scenario.payload or {}
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}('{invalid_path}', json=payload, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{invalid_path}', json=payload)")
    else:
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}('{invalid_path}', headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{invalid_path}')")
    lines.append(f"    assert response.status_code in [400, 404, 409, 422, 424]")


def _emit_invalid_input_body(lines, method, path_expr, requires_auth):
    """Emit invalid input (non-existent ID) test body."""
    lines.append(f"    # Invalid input: non-existent resource")
    if requires_auth:
        lines.append(f"    response = client.{method.lower()}({path_expr}, headers=auth_headers)")
    else:
        lines.append(f"    response = client.{method.lower()}({path_expr})")
    lines.append(f"    assert response.status_code == 404")


def _emit_state_conflict_body(lines, method, path_expr, requires_auth, endpoint, scenario):
    """Emit state conflict test body."""
    payload = scenario.payload or {}
    lines.append(f"    # State conflict: resource in invalid state for this operation")
    if method in ("POST", "PUT", "PATCH"):
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload)")
    else:
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}({path_expr}, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}({path_expr})")
    lines.append(f"    assert response.status_code == {scenario.expected_status}")


def _emit_forbidden_role_body(lines, method, path_expr, endpoint, scenario):
    """Emit forbidden role test body."""
    lines.append(f"    # Forbidden role: user lacks required permissions")
    if method in ("POST", "PUT", "PATCH"):
        payload = scenario.payload or {}
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload, headers=forbidden_headers)")
    else:
        lines.append(f"    response = client.{method.lower()}({path_expr}, headers=forbidden_headers)")
    lines.append(f"    assert response.status_code == 403")


def _emit_field_validation_body(lines, method, path_expr, requires_auth, endpoint, scenario):
    """Emit field validation test body."""
    payload = scenario.payload or {}
    payload_str = json.dumps(payload, indent=8)
    lines.append(f"    payload = {payload_str}")
    if requires_auth:
        lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload, headers=auth_headers)")
    else:
        lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload)")
    lines.append(f"    assert response.status_code == 422")
    lines.append(f"    data = response.json()")
    lines.append(f'    assert "detail" in data or "error" in data')


def _emit_boundary_body(lines, method, path_expr, requires_auth, endpoint, scenario):
    """Emit boundary value test body."""
    payload = scenario.payload or {}
    payload_str = json.dumps(payload, indent=8)
    lines.append(f"    payload = {payload_str}")
    if requires_auth:
        lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload, headers=auth_headers)")
    else:
        lines.append(f"    response = client.{method.lower()}({path_expr}, json=payload)")
    lines.append(f"    assert response.status_code == 422")


def _generate_template_test(test_name: str, method: str, path: str,
                             test_type: str, description: str,
                             requires_auth: bool = False,
                             endpoint=None, scenario=None) -> str:
    """Generate template-based test with FieldSpec-driven payloads."""
    test_path = path.replace(":id", "test-id-123")
    expected_status = scenario.expected_status if scenario else 200
    lines = []

    # Determine fixtures needed
    fixtures = ["client"]
    if requires_auth and test_type not in ("no_auth",):
        fixtures.append("auth_headers")
    if test_type == "forbidden_role":
        fixtures.append("forbidden_headers")

    fixture_str = ", ".join(fixtures)
    lines.append(f"def test_{test_name}({fixture_str}):")
    lines.append(f'    """{description}"""')

    if test_type == "positive":
        if method in ("POST", "PUT", "PATCH"):
            payload = _get_payload(endpoint, scenario)
            payload_str = json.dumps(payload, indent=8)
            lines.append(f"    payload = {payload_str}")
            if requires_auth:
                lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload, headers=auth_headers)")
            else:
                lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload)")
            lines.append(f"    assert response.status_code in [200, 201]")
            lines.append(f"    data = response.json()")
            lines.append(f"    assert data is not None")
            # Verify key fields are returned
            if endpoint and endpoint.request_body:
                key_field = endpoint.request_body[0]
                lines.append(f'    assert "{key_field.name}" in data or "id" in data')
        else:
            if requires_auth:
                lines.append(f"    response = client.{method.lower()}('{test_path}', headers=auth_headers)")
            else:
                lines.append(f"    response = client.{method.lower()}('{test_path}')")
            lines.append(f"    assert response.status_code == {expected_status}")
            lines.append(f"    assert response.json() is not None")

    elif test_type == "no_auth":
        if method in ("POST", "PUT", "PATCH"):
            payload = _get_payload(endpoint, scenario)
            payload_str = json.dumps(payload, indent=8)
            lines.append(f"    payload = {payload_str}")
            lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload, headers={{}})")
        else:
            lines.append(f"    response = client.{method.lower()}('{test_path}', headers={{}})")
        lines.append(f"    assert response.status_code in [401, 403]")

    elif test_type == "dependency_failure":
        lines.append(f"    # Dependency failure: skip required setup, verify error handling")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}('{test_path}', headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{test_path}')")
        lines.append(f"    assert response.status_code in [400, 404, 409, 422, 424]")

    elif test_type == "invalid_input":
        invalid_path = path.replace(":id", "nonexistent-id-999")
        lines.append(f"    # Invalid input: non-existent resource")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}('{invalid_path}', headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{invalid_path}')")
        lines.append(f"    assert response.status_code == 404")

    elif test_type == "state_conflict":
        hint = scenario.payload_hint if scenario else {}
        state_field = next(iter(hint), "status") if hint else "status"
        state_value = hint.get(state_field, "completed") if hint else "completed"
        lines.append(f"    # State conflict: attempting operation when {state_field}='{state_value}'")
        lines.append(f"    # This should fail because the resource is in an invalid state")
        if method in ("POST", "PUT", "PATCH"):
            payload = _get_payload(endpoint, scenario)
            payload[state_field] = state_value
            payload_str = json.dumps(payload, indent=8)
            lines.append(f"    payload = {payload_str}")
            if requires_auth:
                lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload, headers=auth_headers)")
            else:
                lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload)")
        else:
            if requires_auth:
                lines.append(f"    response = client.{method.lower()}('{test_path}', headers=auth_headers)")
            else:
                lines.append(f"    response = client.{method.lower()}('{test_path}')")
        lines.append(f"    assert response.status_code == {expected_status}")

    elif test_type == "forbidden_role":
        lines.append(f"    # Forbidden role: user lacks required permissions")
        if method in ("POST", "PUT", "PATCH"):
            payload = _get_payload(endpoint, scenario)
            payload_str = json.dumps(payload, indent=8)
            lines.append(f"    payload = {payload_str}")
            lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload, headers=forbidden_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{test_path}', headers=forbidden_headers)")
        lines.append(f"    assert response.status_code == 403")

    elif test_type == "field_validation":
        hint = scenario.payload_hint if scenario else {}
        omit_field = hint.get("_omit_field") if hint else None
        if omit_field:
            lines.append(f"    # Missing required field: {omit_field}")
            payload = _get_payload(endpoint, scenario)
            payload.pop(omit_field, None)
            payload.pop("_omit_field", None)
        else:
            lines.append(f"    # Invalid field format")
            payload = _get_payload(endpoint, scenario)
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload)")
        lines.append(f"    assert response.status_code == 422")

    elif test_type == "boundary_value":
        hint = scenario.payload_hint if scenario else {}
        field_name = next(iter(hint), "field") if hint else "field"
        field_value = hint.get(field_name, "x") if hint else "x"
        lines.append(f"    # Boundary value: {field_name} is too short")
        payload = _get_payload(endpoint, scenario)
        payload[field_name] = field_value
        payload_str = json.dumps(payload, indent=8)
        lines.append(f"    payload = {payload_str}")
        if requires_auth:
            lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload, headers=auth_headers)")
        else:
            lines.append(f"    response = client.{method.lower()}('{test_path}', json=payload)")
        lines.append(f"    assert response.status_code == 422")

    return "\n".join(lines)


def _get_payload(endpoint, scenario) -> dict:
    """Get a realistic payload from FieldSpec or scenario hint."""
    if scenario and scenario.payload_hint:
        # If we have endpoint fields, start with those and overlay hint
        if endpoint and endpoint.request_body:
            payload = fields_to_payload(endpoint.request_body)
            for k, v in scenario.payload_hint.items():
                if k != "_omit_field":
                    payload[k] = v
            return payload
        return dict(scenario.payload_hint)

    if endpoint and endpoint.request_body:
        return fields_to_payload(endpoint.request_body)

    # Absolute fallback
    return {"name": "Test Item", "description": "Test description"}
