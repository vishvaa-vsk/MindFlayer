"""Endpoint workflow inference.

Infers CRUD lifecycle workflows from endpoint metadata:
- Collection CRUD: Create → Read → Update → Delete
- Sub-resource actions: Create → [Read →] Action (approve, reject, etc.)
- Cross-resource flows based on dependency graph edges

Produces ordered workflows that feed into test ordering and
precondition injection.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from models.context import SystemContext, Endpoint
from validator.models import (
    CrudVerb,
    DependencyGraph,
    ResourceNode,
    WorkflowEdge,
)

logger = logging.getLogger(__name__)


class EndpointWorkflow:
    """An inferred workflow — an ordered sequence of endpoint invocations
    that represents a typical business flow.

    Example: "Purchase Order Lifecycle"
    → POST /purchase_orders
    → GET /purchase_orders/:id
    → POST /purchase_orders/:id/approve
    → POST /purchase_orders/:id/process_payment
    """

    def __init__(self, name: str, resource: str, steps: list[str] | None = None):
        self.name = name
        self.resource = resource
        self.steps: list[str] = steps or []

    def __repr__(self):
        return f"Workflow({self.name}: {' → '.join(self.steps)})"


def infer_workflows(
    context: SystemContext,
    graph: DependencyGraph,
) -> list[EndpointWorkflow]:
    """Infer ordered business workflows from endpoints and dependency graph.

    For each resource, produces a canonical CRUD lifecycle workflow,
    plus any sub-action workflows.

    Args:
        context: SystemContext with endpoints
        graph: DependencyGraph from dependency_graph module

    Returns:
        List of EndpointWorkflow objects ordered by dependency depth
    """
    workflows: list[EndpointWorkflow] = []
    ep_lookup = {ep.name: ep for ep in context.endpoints}

    for resource_node in graph.resources:
        # ── 1. Canonical CRUD lifecycle ───────────────────
        crud_flow = _build_crud_workflow(resource_node, ep_lookup)
        if crud_flow:
            workflows.append(crud_flow)

        # ── 2. Action workflows ───────────────────────────
        action_flows = _build_action_workflows(resource_node, ep_lookup, graph)
        workflows.extend(action_flows)

    return workflows


def infer_endpoint_order(
    context: SystemContext,
    graph: DependencyGraph,
) -> list[str]:
    """Produce a globally ordered list of endpoint names.

    Uses topological sort on the dependency graph, falling back to
    CRUD verb priority (CREATE < READ < UPDATE < ACTION < DELETE).

    Returns:
        List of endpoint names in recommended execution order
    """
    # Build in-degree map
    in_degree: dict[str, int] = {ep.name: 0 for ep in context.endpoints}
    for edge in graph.edges:
        if edge.target in in_degree:
            in_degree[edge.target] += 1

    # Kahn's algorithm with priority tie-breaking
    ep_lookup = {ep.name: ep for ep in context.endpoints}
    queue: list[str] = []
    for name, deg in in_degree.items():
        if deg == 0:
            queue.append(name)

    # Sort queue by CRUD priority
    queue.sort(key=lambda n: _crud_priority(ep_lookup.get(n)))
    ordered: list[str] = []

    while queue:
        node = queue.pop(0)
        ordered.append(node)

        # Decrease in-degree for dependents
        for dependent in graph.reverse_adj.get(node, []):
            if dependent in in_degree:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
                    queue.sort(key=lambda n: _crud_priority(ep_lookup.get(n)))

    # Add any endpoints not yet visited (cycle or disconnected)
    remaining = [ep.name for ep in context.endpoints if ep.name not in set(ordered)]
    remaining.sort(key=lambda n: _crud_priority(ep_lookup.get(n)))
    ordered.extend(remaining)

    return ordered


def get_setup_chain(
    endpoint_name: str,
    graph: DependencyGraph,
    ep_lookup: dict[str, Endpoint],
) -> list[str]:
    """Get the ordered chain of endpoints that must be called before
    `endpoint_name` can be tested (its transitive dependencies).

    Uses BFS on the adjacency list (target → sources).

    Returns:
        List of endpoint names in execution order (dependencies first)
    """
    visited: set[str] = set()
    chain: list[str] = []

    def _dfs(name: str):
        if name in visited:
            return
        visited.add(name)
        for dep in graph.adjacency.get(name, []):
            _dfs(dep)
        chain.append(name)

    _dfs(endpoint_name)
    # Remove the endpoint itself — we only want its setup
    if chain and chain[-1] == endpoint_name:
        chain.pop()

    return chain


# ── Internal helpers ──────────────────────────────────────

_CRUD_PRIORITY = {
    CrudVerb.CREATE: 0,
    CrudVerb.READ: 1,
    CrudVerb.UPDATE: 2,
    CrudVerb.ACTION: 3,
    CrudVerb.DELETE: 4,
}


def _crud_priority(ep: Endpoint | None) -> int:
    """Get sort priority for an endpoint based on its CRUD verb."""
    if ep is None:
        return 99
    verb = CrudVerb.from_http_method(ep.method, ep.url_path)
    return _CRUD_PRIORITY.get(verb, 99)


def _build_crud_workflow(
    resource: ResourceNode,
    ep_lookup: dict[str, Endpoint],
) -> EndpointWorkflow | None:
    """Build the canonical Create→Read→Update→Delete workflow for a resource."""
    steps = []
    for verb in [CrudVerb.CREATE, CrudVerb.READ, CrudVerb.UPDATE, CrudVerb.DELETE]:
        ep_name = resource.crud_map.get(verb.value)
        if ep_name and ep_name in ep_lookup:
            steps.append(ep_name)

    if not steps:
        return None

    return EndpointWorkflow(
        name=f"{resource.name}_crud_lifecycle",
        resource=resource.name,
        steps=steps,
    )


def _build_action_workflows(
    resource: ResourceNode,
    ep_lookup: dict[str, Endpoint],
    graph: DependencyGraph,
) -> list[EndpointWorkflow]:
    """Build workflows for sub-resource actions (approve, reject, etc.)."""
    workflows = []

    for key, ep_name in resource.crud_map.items():
        if not key.startswith("action_"):
            continue
        action_name = key.replace("action_", "")

        # Build setup chain from dependency graph
        chain = get_setup_chain(ep_name, graph, ep_lookup)
        steps = chain + [ep_name]

        workflows.append(EndpointWorkflow(
            name=f"{resource.name}_{action_name}_workflow",
            resource=resource.name,
            steps=steps,
        ))

    return workflows
