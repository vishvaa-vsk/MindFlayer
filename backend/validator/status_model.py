"""Status transition model.

Infers a state machine for each resource from StateConstraint metadata
and endpoint relationships. Used to:
- Generate state-conflict tests with valid from-states
- Ensure action tests transition through proper states
- Validate that test sequences follow valid state paths
"""
from __future__ import annotations

import logging
from collections import defaultdict

from models.context import SystemContext, Endpoint, StateConstraint
from validator.models import StatusTransition, StatusModel, CrudVerb, DependencyGraph

logger = logging.getLogger(__name__)

# ── Default state inferences ──────────────────────────────
# Maps action path segments to (from_status, to_status)
DEFAULT_ACTION_TRANSITIONS: dict[str, tuple[str, str]] = {
    "approve": ("pending", "approved"),
    "reject": ("pending", "rejected"),
    "cancel": ("pending", "cancelled"),
    "process_payment": ("approved", "paid"),
    "ship": ("paid", "shipped"),
    "deliver": ("shipped", "delivered"),
    "complete": ("in_progress", "completed"),
    "archive": ("completed", "archived"),
    "activate": ("draft", "active"),
    "deactivate": ("active", "inactive"),
    "submit": ("draft", "submitted"),
    "review": ("submitted", "in_review"),
    "publish": ("in_review", "published"),
    "close": ("open", "closed"),
    "reopen": ("closed", "open"),
}


def build_status_models(
    context: SystemContext,
    graph: DependencyGraph,
) -> list[StatusModel]:
    """Build state machines for resources that have state transitions.

    Sources of state info (in priority order):
    1. Explicit StateConstraint on endpoints
    2. Inferred from action endpoint names (approve → pending→approved)
    3. Default CREATE → initial state

    Args:
        context: SystemContext with endpoints
        graph: DependencyGraph for resource grouping

    Returns:
        List of StatusModel (one per resource with state transitions)
    """
    ep_lookup = {ep.name: ep for ep in context.endpoints}
    resource_transitions: dict[str, list[StatusTransition]] = defaultdict(list)
    resource_statuses: dict[str, set[str]] = defaultdict(set)

    for resource_node in graph.resources:
        resource_name = resource_node.name

        # ── 1. From explicit StateConstraints ─────────────
        for ep_name in resource_node.endpoints:
            ep = ep_lookup.get(ep_name)
            if not ep:
                continue
            for constraint in ep.state_constraints:
                for allowed in constraint.allowed_values:
                    resource_statuses[resource_name].add(allowed)
                for blocked in constraint.blocked_values:
                    resource_statuses[resource_name].add(blocked)

        # ── 2. From action endpoint names ─────────────────
        for key, ep_name in resource_node.crud_map.items():
            if not key.startswith("action_"):
                continue
            action = key.replace("action_", "")
            if action in DEFAULT_ACTION_TRANSITIONS:
                from_s, to_s = DEFAULT_ACTION_TRANSITIONS[action]
                resource_transitions[resource_name].append(StatusTransition(
                    resource=resource_name,
                    from_status=from_s,
                    to_status=to_s,
                    via_endpoint=ep_name,
                ))
                resource_statuses[resource_name].update([from_s, to_s])

        # ── 3. Default CREATE → initial state ────────────
        create_ep = resource_node.crud_map.get(CrudVerb.CREATE.value)
        if create_ep:
            # If we have action-inferred transitions, use their earliest from_status
            # Otherwise default to "created"
            initial = "created"
            if resource_transitions[resource_name]:
                # Find statuses that appear as from_status but never as to_status
                from_states = {t.from_status for t in resource_transitions[resource_name]}
                to_states = {t.to_status for t in resource_transitions[resource_name]}
                root_states = from_states - to_states
                if root_states:
                    initial = sorted(root_states)[0]
            resource_statuses[resource_name].add(initial)

    # ── Build StatusModel objects ─────────────────────────
    models: list[StatusModel] = []
    for resource_name in resource_statuses:
        transitions = resource_transitions.get(resource_name, [])
        statuses = sorted(resource_statuses[resource_name])

        # Terminal statuses: appear as to_status but not as from_status
        from_set = {t.from_status for t in transitions}
        to_set = {t.to_status for t in transitions}
        terminal = sorted(to_set - from_set) if transitions else []

        # Determine initial status
        initial = "created"
        root_states = from_set - to_set
        if root_states:
            initial = sorted(root_states)[0]

        models.append(StatusModel(
            resource=resource_name,
            initial_status=initial,
            statuses=statuses,
            transitions=transitions,
            terminal_statuses=terminal,
        ))

    return models


def get_valid_transition_path(
    model: StatusModel,
    target_status: str,
) -> list[StatusTransition]:
    """Find the shortest path from initial_status to target_status.

    Uses BFS on the transition graph.

    Args:
        model: StatusModel for the resource
        target_status: The desired state to reach

    Returns:
        List of StatusTransition in order, or empty if unreachable
    """
    if target_status == model.initial_status:
        return []

    # BFS
    adjacency: dict[str, list[StatusTransition]] = defaultdict(list)
    for t in model.transitions:
        adjacency[t.from_status].append(t)

    queue: list[tuple[str, list[StatusTransition]]] = [(model.initial_status, [])]
    visited: set[str] = {model.initial_status}

    while queue:
        current, path = queue.pop(0)
        for transition in adjacency.get(current, []):
            if transition.to_status in visited:
                continue
            new_path = path + [transition]
            if transition.to_status == target_status:
                return new_path
            visited.add(transition.to_status)
            queue.append((transition.to_status, new_path))

    return []  # Unreachable
