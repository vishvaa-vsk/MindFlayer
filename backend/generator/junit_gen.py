"""JUnit XML report generator with expected_status support."""
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString
from models.test_plan import TestPlan
from models.context import SystemContext


def generate_junit_xml(test_plan: TestPlan, context: SystemContext | None = None) -> str:
    """
    Generate JUnit XML report from a test plan.

    Uses expected_status from TestScenario for accurate assertions
    instead of hard-coded status code mappings.

    Args:
        test_plan: TestPlan with scenarios
        context: SystemContext for endpoint metadata

    Returns:
        JUnit XML string (CI/CD compatible)
    """
    endpoint_lookup = {}
    if context:
        for ep in context.endpoints:
            endpoint_lookup[ep.name] = ep

    # Group scenarios by endpoint for test suites
    endpoint_groups: dict[str, list] = {}
    for scenario in test_plan.scenarios:
        if scenario.endpoint not in endpoint_groups:
            endpoint_groups[scenario.endpoint] = []
        endpoint_groups[scenario.endpoint].append(scenario)

    root = Element("testsuites")
    root.set("name", "MindFlayer Generated Tests")
    root.set("tests", str(len(test_plan.scenarios)))

    for endpoint_name, scenarios in endpoint_groups.items():
        ep = endpoint_lookup.get(endpoint_name)
        method = ep.method if ep else "GET"
        path = ep.url_path if ep else "/"

        suite = SubElement(root, "testsuite")
        suite.set("name", f"{method} {path}")
        suite.set("tests", str(len(scenarios)))

        for scenario in scenarios:
            testcase = SubElement(suite, "testcase")
            testcase.set("name", f"test_{scenario.test_name}")
            testcase.set("classname", f"mindflayer.{endpoint_name}")

            # Properties with enriched metadata
            props = SubElement(testcase, "properties")

            _add_prop(props, "test_type", scenario.test_type)
            _add_prop(props, "http_method", method)
            _add_prop(props, "endpoint_path", path)
            _add_prop(props, "expected_status", str(scenario.expected_status))
            _add_prop(props, "description", scenario.description)
            _add_prop(props, "generator", "MindFlayer")

            # Add payload hint if present
            if scenario.payload_hint:
                import json
                _add_prop(props, "payload_hint", json.dumps(scenario.payload_hint))

            # Add field info for validation tests
            if scenario.test_type in ("field_validation", "boundary_value") and ep:
                field_names = ", ".join(f.name for f in ep.request_body)
                _add_prop(props, "request_fields", field_names)

            # For negative tests, add a skipped-style marker showing expected failure
            if scenario.test_type in ("no_auth", "state_conflict", "forbidden_role",
                                        "field_validation", "boundary_value",
                                        "dependency_failure", "invalid_input"):
                system_out = SubElement(testcase, "system-out")
                system_out.text = (
                    f"Expected: HTTP {scenario.expected_status}\n"
                    f"Scenario: {scenario.description}\n"
                    f"Type: {scenario.test_type}"
                )

    xml_str = tostring(root, encoding="unicode")
    # Pretty print
    try:
        return parseString(xml_str).toprettyxml(indent="  ", encoding=None)
    except Exception:
        return f'<?xml version="1.0" ?>\n{xml_str}'


def _add_prop(props_element: Element, name: str, value: str) -> None:
    """Add a property element to the properties container."""
    prop = SubElement(props_element, "property")
    prop.set("name", name)
    prop.set("value", value)
