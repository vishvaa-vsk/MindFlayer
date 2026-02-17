"""Resource dependency graph builder.

Analyzes SystemContext endpoints to build a graph of resource dependencies:
- Extracts logical resources from URL paths
- Maps CRUD operations to resources
- Identifies implicit dependencies (e.g., GET :id needs a CREATE first)
- Merges with explicit depends_on declarations
"""
from __future__ import annotations

import re
import logging
from collections import defaultdict

from models.context import SystemContext, Endpoint
from validator.models import (
    CrudVerb,
    ResourceNode,
    WorkflowEdge,
    DependencyGraph,
)

logger = logging.getLogger(__name__)


def build_dependency_graph(context: SystemContext) -> DependencyGraph:
    """Build a complete resource dependency graph from SystemContext.

    Steps:
    1. Extract resources from endpoint paths
    2. Map CRUD operations per resource
    3. Infer implicit dependencies (READ/UPDATE/DELETE → CREATE)
    4. Merge explicit depends_on declarations
    5. Compute adjacency lists

    Args:
        context: SystemContext with all endpoints

    Returns:
        DependencyGraph with resources, edges, and adjacency lists
    """
    # Step 1: Extract resources
    resources = _extract_resources(context.endpoints)

    # Step 2: Map CRUD operations
    _map_crud_operations(resources, context.endpoints)

    # Step 3 & 4: Build edges
    edges = _build_edges(resources, context.endpoints)

    # Step 5: Compute adjacency
    adjacency: dict[str, list[str]] = defaultdict(list)
    reverse_adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.source not in adjacency[edge.target]:
            adjacency[edge.target].append(edge.source)
        if edge.target not in reverse_adj[edge.source]:
            reverse_adj[edge.source].append(edge.target)

    return DependencyGraph(
        resources=list(resources.values()),
        edges=edges,
        adjacency=dict(adjacency),
        reverse_adj=dict(reverse_adj),
    )


def _extract_resources(endpoints: list[Endpoint]) -> dict[str, ResourceNode]:
    """Extract logical resources from endpoint URL paths.

    Heuristic: the first path segment after / is the resource name.
    /purchase_orders → "purchase_orders"
    /purchase_orders/:id → "purchase_orders"
    /purchase_orders/:id/approve → "purchase_orders" (sub-action)
    /vendors/:id → "vendors"
    """
    resources: dict[str, ResourceNode] = {}

    for ep in endpoints:
        resource_name = _path_to_resource(ep.url_path)
        if not resource_name:
            continue

        if resource_name not in resources:
            resources[resource_name] = ResourceNode(
                name=resource_name,
                collection_path=f"/{resource_name}",
            )

        node = resources[resource_name]
        node.endpoints.append(ep.name)

        # Detect item path
        if ":id" in ep.url_path and node.item_path is None:
            # Extract the item path pattern (e.g., /purchase_orders/:id)
            parts = ep.url_path.split("/")
            item_parts = []
            for part in parts:
                item_parts.append(part)
                if part == ":id":
                    break
            node.item_path = "/".join(item_parts)

    return resources


def _map_crud_operations(
    resources: dict[str, ResourceNode],
    endpoints: list[Endpoint],
) -> None:
    """Map each endpoint to its CRUD verb on its resource."""
    for ep in endpoints:
        resource_name = _path_to_resource(ep.url_path)
        if resource_name not in resources:
            continue

        verb = CrudVerb.from_http_method(ep.method, ep.url_path)
        node = resources[resource_name]

        # Only set if not already mapped (first endpoint wins for each verb)
        if verb.value not in node.crud_map:
            node.crud_map[verb.value] = ep.name
        elif verb == CrudVerb.ACTION:
            # Multiple actions are allowed — use a list-like key
            action_name = _extract_action_name(ep.url_path)
            node.crud_map[f"action_{action_name}"] = ep.name


def _build_edges(
    resources: dict[str, ResourceNode],
    endpoints: list[Endpoint],
) -> list[WorkflowEdge]:
    """Build dependency edges from CRUD semantics and explicit depends_on.

    Implicit rules:
    - READ item → depends on CREATE (need an ID)
    - UPDATE item → depends on CREATE
    - DELETE item → depends on CREATE
    - ACTION on item → depends on READ (must verify it exists)
    """
    edges: list[WorkflowEdge] = []
    seen: set[tuple[str, str]] = set()

    def _add_edge(source: str, target: str, resource: str, reason: str):
        if (source, target) not in seen and source != target:
            edges.append(WorkflowEdge(
                source=source,
                target=target,
                resource=resource,
                reason=reason,
            ))
            seen.add((source, target))

    # ── Implicit CRUD dependencies ────────────────────────
    for resource_name, node in resources.items():
        create_ep = node.crud_map.get(CrudVerb.CREATE.value)
        read_ep = node.crud_map.get(CrudVerb.READ.value)

        if create_ep:
            # READ → CREATE
            if read_ep:
                _add_edge(
                    create_ep, read_ep, resource_name,
                    f"GET requires existing {resource_name} (created by POST)",
                )
            # UPDATE → CREATE
            update_ep = node.crud_map.get(CrudVerb.UPDATE.value)
            if update_ep:
                _add_edge(
                    create_ep, update_ep, resource_name,
                    f"PUT requires existing {resource_name} (created by POST)",
                )
            # DELETE → CREATE
            delete_ep = node.crud_map.get(CrudVerb.DELETE.value)
            if delete_ep:
                _add_edge(
                    create_ep, delete_ep, resource_name,
                    f"DELETE requires existing {resource_name} (created by POST)",
                )

        # ACTION → READ (verify existence before acting)
        for key, action_ep in node.crud_map.items():
            if key.startswith("action_"):
                dep = read_ep or create_ep
                if dep:
                    _add_edge(
                        dep, action_ep, resource_name,
                        f"Action requires existing {resource_name}",
                    )

    # ── Explicit depends_on ───────────────────────────────
    ep_lookup = {ep.name: ep for ep in endpoints}
    for ep in endpoints:
        for dep_name in ep.depends_on:
            if dep_name in ep_lookup:
                resource = _path_to_resource(ep.url_path)
                _add_edge(
                    dep_name, ep.name, resource,
                    f"Explicit dependency declared: {ep.name} depends on {dep_name}",
                )

    return edges


# ── Path helpers ──────────────────────────────────────────

def _path_to_resource(url_path: str) -> str:
    """Extract the primary resource name from a URL path.

    /purchase_orders → "purchase_orders"
    /purchase_orders/:id/approve → "purchase_orders"
    /audit_logs → "audit_logs"
    """
    parts = [p for p in url_path.split("/") if p and p != ":id"]
    return parts[0] if parts else ""


def _extract_action_name(url_path: str) -> str:
    """Extract sub-action name from path like /resource/:id/approve → 'approve'."""
    parts = url_path.rstrip("/").split("/")
    # Last segment that isn't :id
    for part in reversed(parts):
        if part and part != ":id" and not part.startswith(":"):
            return part
    return "unknown"
