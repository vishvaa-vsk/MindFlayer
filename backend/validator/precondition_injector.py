"""Precondition injector.

For each test scenario, determines what setup steps are needed and
injects Precondition metadata. Generators then translate these into:
- pytest: fixture calls or inline setup code
- Postman: pre-request scripts
- Gherkin: Given steps
- JUnit: @Before methods

This is the key improvement — tests like "GET /orders/:id" automatically
get a precondition to "POST /orders" and capture the created ID.
"""
from __future__ import annotations

import logging
from models.context import SystemContext, Endpoint
from context.schema_inference import fields_to_payload
from validator.models import (
    CrudVerb,
    DependencyGraph,
    Precondition,
    ValidatedScenario,
    StatusModel,
    StatusTransition,
)
from validator.workflow_inference import get_setup_chain
from validator.status_model import get_valid_transition_path

logger = logging.getLogger(__name__)


def inject_preconditions(
    scenarios: list[ValidatedScenario],
    context: SystemContext,
    graph: DependencyGraph,
    status_models: list[StatusModel],
) -> list[ValidatedScenario]:
    """Inject precondition metadata into all scenarios.

    Rules:
    1. Positive tests for READ/UPDATE/DELETE/ACTION endpoints need
       a CREATE precondition to produce a valid resource ID.
    2. State-conflict tests need transitions to bring the resource
       to the required state before testing the conflict.
    3. Dependency-failure tests get NO preconditions (that's the point).
    4. No-auth / invalid-input tests may need a resource if the endpoint
       requires an existing ID.

    Args:
        scenarios: List of ValidatedScenario to enrich
        context: SystemContext for endpoint metadata
        graph: DependencyGraph for dependency chains
        status_models: StatusModel list for state transitions

    Returns:
        Same list with preconditions and variable_refs populated
    """
    ep_lookup = {ep.name: ep for ep in context.endpoints}
    status_lookup = {m.resource: m for m in status_models}
    injected_count = 0

    for scenario in scenarios:
        ep = ep_lookup.get(scenario.endpoint)
        if not ep:
            continue

        verb = CrudVerb.from_http_method(ep.method, ep.url_path)

        # Skip injection for certain test types
        if scenario.test_type == "dependency_failure":
            continue  # Deliberately no setup

        if scenario.test_type in ("field_validation", "boundary_value"):
            # These test payload validity — may still need a resource for PUT/PATCH
            if verb in (CrudVerb.UPDATE, CrudVerb.DELETE):
                _inject_create_precondition(scenario, ep, ep_lookup, graph)
                injected_count += 1
            continue

        if scenario.test_type == "no_auth":
            # For item endpoints, inject a create step (so the test URL is valid)
            if ":id" in ep.url_path and verb != CrudVerb.CREATE:
                _inject_create_precondition(scenario, ep, ep_lookup, graph)
                injected_count += 1
            continue

        if scenario.test_type == "invalid_input":
            continue  # Uses fake IDs intentionally

        if scenario.test_type == "forbidden_role":
            # Need a real resource for item endpoints
            if ":id" in ep.url_path and verb != CrudVerb.CREATE:
                _inject_create_precondition(scenario, ep, ep_lookup, graph)
                injected_count += 1
            continue

        # ── Positive / state_conflict tests ───────────────
        if verb in (CrudVerb.READ, CrudVerb.UPDATE, CrudVerb.DELETE, CrudVerb.ACTION):
            _inject_create_precondition(scenario, ep, ep_lookup, graph)
            injected_count += 1

        # State-conflict: need to transition resource to the right state
        if scenario.test_type == "state_conflict":
            resource = _path_to_resource(ep.url_path)
            model = status_lookup.get(resource)
            if model and scenario.payload:
                _inject_state_transitions(scenario, model, ep_lookup, graph)

    logger.info("[precondition_injector] Injected %d preconditions across %d scenarios",
                injected_count, len(scenarios))
    return scenarios


def _inject_create_precondition(
    scenario: ValidatedScenario,
    endpoint: Endpoint,
    ep_lookup: dict[str, Endpoint],
    graph: DependencyGraph,
) -> None:
    """Inject CREATE precondition for an endpoint that operates on an item.

    Finds the CREATE endpoint for the same resource and adds a precondition
    that calls it and captures the ID.
    """
    resource = _path_to_resource(endpoint.url_path)

    # Find the CREATE endpoint through the dependency graph
    setup_chain = get_setup_chain(endpoint.name, graph, ep_lookup)

    for dep_name in setup_chain:
        dep_ep = ep_lookup.get(dep_name)
        if not dep_ep:
            continue

        dep_verb = CrudVerb.from_http_method(dep_ep.method, dep_ep.url_path)

        # Build payload for the setup endpoint
        payload = None
        if dep_ep.request_body:
            payload = fields_to_payload(dep_ep.request_body)

        # Determine what to extract from the response
        extract_field = None
        variable_name = None
        if dep_verb == CrudVerb.CREATE:
            extract_field = "id"
            variable_name = f"{resource}_id"

        precondition = Precondition(
            endpoint_name=dep_ep.name,
            method=dep_ep.method,
            path=dep_ep.url_path,
            payload=payload,
            extract_field=extract_field,
            variable_name=variable_name,
            description=f"Setup: {dep_ep.method} {dep_ep.url_path} → capture {extract_field or 'response'}",
        )
        scenario.preconditions.append(precondition)

        # Register variable reference
        if variable_name and extract_field:
            scenario.variable_refs[f":{resource}_id"] = variable_name
            # Also map :id in the URL
            scenario.variable_refs[":id"] = variable_name


def _inject_state_transitions(
    scenario: ValidatedScenario,
    model: StatusModel,
    ep_lookup: dict[str, Endpoint],
    graph: DependencyGraph,
) -> None:
    """Inject state transition preconditions for state-conflict tests.

    Finds the path from initial state to the target conflict state
    and injects preconditions for each transition.
    """
    # Find which state the test expects
    target_field = None
    target_value = None
    for field_name, value in (scenario.payload or {}).items():
        if field_name in ("status", "state"):
            target_value = str(value)
            target_field = field_name
            break

    if not target_value:
        return

    # Find path from initial to target state
    path = get_valid_transition_path(model, target_value)
    for transition in path:
        ep = ep_lookup.get(transition.via_endpoint)
        if not ep:
            continue

        payload = None
        if ep.request_body:
            payload = fields_to_payload(ep.request_body)

        precondition = Precondition(
            endpoint_name=ep.name,
            method=ep.method,
            path=ep.url_path,
            payload=payload,
            description=f"Transition: {transition.from_status} → {transition.to_status} via {ep.method} {ep.url_path}",
        )
        scenario.preconditions.append(precondition)


def _path_to_resource(url_path: str) -> str:
    """Extract resource name from URL path."""
    parts = [p for p in url_path.split("/") if p and p != ":id"]
    return parts[0] if parts else ""
