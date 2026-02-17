"""Test ordering engine.

Sorts test scenarios by dependency priority so that:
- Tests creating resources run before tests consuming them
- Positive tests run before failure/negative tests
- Within a resource group, CRUD order is respected
- Cross-resource dependencies are resolved via topological sort

This is format-agnostic — generators use the order to emit tests
in the correct sequence regardless of output format.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from models.context import SystemContext, Endpoint
from models.test_plan import TestScenario
from validator.models import (
    CrudVerb,
    DependencyGraph,
    ValidatedScenario,
)
from validator.workflow_inference import infer_endpoint_order

logger = logging.getLogger(__name__)


# ── Test type priority (lower = earlier) ──────────────────
_TEST_TYPE_PRIORITY: dict[str, int] = {
    "positive": 0,           # Must succeed first — other tests need its side effects
    "field_validation": 1,   # Schema validation (no resources needed)
    "boundary_value": 2,     # Schema validation (no resources needed)
    "no_auth": 3,            # Auth check (no resources needed)
    "forbidden_role": 4,     # Auth check
    "invalid_input": 5,      # 404 — no setup needed
    "dependency_failure": 6, # Intentionally missing setup
    "state_conflict": 7,     # Needs resource in specific state
}


def order_scenarios(
    scenarios: list[ValidatedScenario],
    context: SystemContext,
    graph: DependencyGraph,
) -> list[ValidatedScenario]:
    """Sort validated scenarios in optimal execution order.

    Sorting criteria (in priority):
    1. Endpoint dependency order (topological sort)
    2. Test type priority (positive before negative)
    3. Stable secondary sort by test name

    Args:
        scenarios: List of ValidatedScenario to order
        context: SystemContext for endpoint metadata
        graph: DependencyGraph for dependency resolution

    Returns:
        Sorted list of ValidatedScenario with order_priority set
    """
    # Get global endpoint order
    endpoint_order = infer_endpoint_order(context, graph)
    ep_rank = {name: idx for idx, name in enumerate(endpoint_order)}

    # Sort
    def _sort_key(s: ValidatedScenario) -> tuple[int, int, str]:
        ep_idx = ep_rank.get(s.endpoint, 999)
        type_idx = _TEST_TYPE_PRIORITY.get(s.test_type, 99)
        return (ep_idx, type_idx, s.test_name)

    sorted_scenarios = sorted(scenarios, key=_sort_key)

    # Set order_priority
    for i, scenario in enumerate(sorted_scenarios):
        scenario.order_priority = i

    # Set resource group
    ep_lookup = {ep.name: ep for ep in context.endpoints}
    for scenario in sorted_scenarios:
        ep = ep_lookup.get(scenario.endpoint)
        if ep:
            parts = [p for p in ep.url_path.split("/") if p and p != ":id"]
            scenario.group = parts[0] if parts else "unknown"

    reordered = sum(
        1 for a, b in zip(scenarios, sorted_scenarios) if a.test_name != b.test_name
    )
    if reordered > 0:
        logger.info("[test_ordering] Reordered %d/%d scenarios", reordered, len(scenarios))

    return sorted_scenarios


def group_by_resource(
    scenarios: list[ValidatedScenario],
) -> dict[str, list[ValidatedScenario]]:
    """Group ordered scenarios by resource for parallel execution.

    Tests within a resource group must be sequential (they may share state),
    but different resource groups can run in parallel.
    """
    groups: dict[str, list[ValidatedScenario]] = defaultdict(list)
    for s in scenarios:
        groups[s.group or "ungrouped"].append(s)
    return dict(groups)


def compute_reorder_count(
    original: list[TestScenario],
    ordered: list[ValidatedScenario],
) -> int:
    """Count how many scenarios changed position after ordering."""
    original_order = {s.test_name: i for i, s in enumerate(original)}
    moved = 0
    for i, s in enumerate(ordered):
        if original_order.get(s.test_name, -1) != i:
            moved += 1
    return moved
