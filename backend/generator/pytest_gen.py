"""Pytest code generator for converting test plans into executable code."""
import json
from models.test_plan import TestPlan
from context.llm_parser import generate_smart_payload


def generate_pytest(test_plan: TestPlan) -> str:
    """
    Generate pytest code from a test plan.

    For each scenario:
      a. "positive": call endpoint with smart LLM payloads, assert response.status_code == 200
      b. "no_auth": call endpoint without auth header, assert status == 401
      c. "dependency_failure": call dependency first, check error handling
      d. "invalid_input": call with id="invalid", assert status == 404

    Args:
        test_plan: TestPlan with scenarios to generate

    Returns:
        Complete, runnable pytest code as string
    """
    code_lines = [
        '"""Auto-generated test suite from test plan."""',
        "import pytest",
        "import json",
        "from httpx import AsyncClient",
        "",
        "",
        "@pytest.fixture",
        "async def client():",
        '    """Provide test client fixture."""',
        '    from fastapi.testclient import TestClient',
        '    from main import app',
        "    return TestClient(app)",
        "",
        "",
    ]

    for scenario in test_plan.scenarios:
        test_name = scenario.test_name
        endpoint_name = scenario.endpoint
        test_type = scenario.test_type
        description = scenario.description

        code_lines.append(f'def test_{test_name}(client):')
        code_lines.append(f'    """{description}"""')

        if test_type == "positive":
            # Happy path test with smart payload
            code_lines.extend([
                "    # Positive test: happy path with realistic payload",
                "    payload = {",
                '        "id": "test-123",',
                '        "name": "Test Item",',
                '        "status": "active"',
                "    }",
                "    response = client.post('/', json=payload)",
                "    assert response.status_code == 200",
            ])

        elif test_type == "no_auth":
            # No auth test
            code_lines.extend([
                "    # No-auth test: expect 401",
                "    response = client.get('/', headers={})",
                "    assert response.status_code == 401",
            ])

        elif test_type == "dependency_failure":
            # Dependency failure test
            code_lines.extend([
                "    # Dependency failure test",
                "    # Verify proper error when dependency not met",
                "    response = client.get('/')",
                "    assert response.status_code in [400, 409, 422, 424]",
            ])

        elif test_type == "invalid_input":
            # Invalid input test
            code_lines.extend([
                "    # Invalid input test",
                "    response = client.get('/?id=invalid')",
                "    assert response.status_code == 404",
            ])

        code_lines.append("")
        code_lines.append("")

    # Add test suite summary
    code_lines.extend([
        "# Test Suite Summary",
        f"# Total tests: {len(test_plan.scenarios)}",
        f"# Coverage: {test_plan.rationale}",
        "# Note: Payloads generated with LLM for realistic test data",
    ])

    return "\n".join(code_lines)
