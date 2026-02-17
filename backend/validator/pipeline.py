"""Validation pipeline — orchestrates all validation layer components.

This is the main entry point for the validation layer. It chains:
1. Dependency graph building
2. Workflow inference
3. Status model construction
4. Scenario enrichment (type enforcement + precondition injection)
5. Test ordering
6. Post-generation AST checking + repair

Usage in the generation pipeline:
    context → plan → validate(plan, context) → ValidatedTestPlan → generator → AST check

All generators should consume ValidatedTestPlan instead of raw TestPlan.
"""
from __future__ import annotations

import logging
from models.context import SystemContext
from models.test_plan import TestPlan, TestScenario
from context.schema_inference import fields_to_payload

from validator.models import (
    ValidatedScenario,
    ValidatedTestPlan,
    ValidationReport,
    SyntaxIssue,
)
from validator.dependency_graph import build_dependency_graph
from validator.workflow_inference import infer_workflows
from validator.status_model import build_status_models
from validator.type_enforcer import enforce_types
from validator.test_ordering import order_scenarios, compute_reorder_count
from validator.precondition_injector import inject_preconditions
from validator.ast_checker import check_syntax, repair_python_syntax

logger = logging.getLogger(__name__)


def validate_plan(
    test_plan: TestPlan,
    context: SystemContext,
) -> ValidatedTestPlan:
    """Run the full validation pipeline on a test plan.

    Transforms raw TestPlan → ValidatedTestPlan with:
    - Dependency-resolved preconditions
    - Type-checked payloads
    - Optimal test ordering
    - Validation report

    Args:
        test_plan: Raw TestPlan from the planner
        context: SystemContext for endpoint metadata

    Returns:
        ValidatedTestPlan ready for generators
    """
    ep_lookup = {ep.name: ep for ep in context.endpoints}

    # ── Step 1: Build dependency graph ────────────────────
    logger.info("[validate] Building dependency graph for %d endpoints", len(context.endpoints))
    graph = build_dependency_graph(context)
    logger.info("[validate] Graph: %d resources, %d edges", len(graph.resources), len(graph.edges))

    # ── Step 2: Infer workflows ───────────────────────────
    workflows = infer_workflows(context, graph)
    logger.info("[validate] Inferred %d workflows", len(workflows))

    # ── Step 3: Build status models ───────────────────────
    status_models = build_status_models(context, graph)
    logger.info("[validate] Built %d status models", len(status_models))

    # ── Step 4: Enrich scenarios ──────────────────────────
    all_type_issues = []
    validated_scenarios: list[ValidatedScenario] = []

    for scenario in test_plan.scenarios:
        ep = ep_lookup.get(scenario.endpoint)

        # Build payload from hint or schema
        payload = _resolve_payload(scenario, ep)

        # Type enforcement
        repaired_payload, type_issues = enforce_types(
            test_name=scenario.test_name,
            payload=payload,
            endpoint=ep,
            test_type=scenario.test_type,
        )
        all_type_issues.extend(type_issues)

        validated_scenarios.append(ValidatedScenario(
            test_name=scenario.test_name,
            endpoint=scenario.endpoint,
            description=scenario.description,
            test_type=scenario.test_type,
            expected_status=scenario.expected_status,
            payload=repaired_payload,
            preconditions=[],
            variable_refs={},
            order_priority=0,
            group="",
            warnings=[issue.suggestion for issue in type_issues],
        ))

    # ── Step 5: Inject preconditions ──────────────────────
    validated_scenarios = inject_preconditions(
        validated_scenarios, context, graph, status_models,
    )

    # ── Step 6: Order scenarios ───────────────────────────
    validated_scenarios = order_scenarios(validated_scenarios, context, graph)
    reordered = compute_reorder_count(test_plan.scenarios, validated_scenarios)

    # ── Build report ──────────────────────────────────────
    injected_count = sum(len(s.preconditions) for s in validated_scenarios)
    report = ValidationReport(
        total_scenarios=len(validated_scenarios),
        syntax_errors=[],  # Filled after generation
        type_mismatches=all_type_issues,
        missing_preconditions=0,
        reordered_count=reordered,
        injected_preconditions=injected_count,
        warnings=[f"Type coercion applied to {len(all_type_issues)} field(s)"] if all_type_issues else [],
    )

    logger.info(
        "[validate] Validated %d scenarios: %d type fixes, %d preconditions, %d reordered",
        len(validated_scenarios), len(all_type_issues), injected_count, reordered,
    )

    return ValidatedTestPlan(
        scenarios=validated_scenarios,
        dependency_graph=graph,
        status_models=status_models,
        report=report,
        rationale=test_plan.rationale,
    )


def validate_output(
    code: str,
    output_format: str = "pytest",
    auto_repair: bool = True,
) -> tuple[str, list[SyntaxIssue], list[str]]:
    """Post-generation validation — check and optionally repair output syntax.

    Args:
        code: Generated code string
        output_format: Output format key (pytest, postman, junit, gherkin, openapi)
        auto_repair: If True, attempt to repair syntax errors (Python only)

    Returns:
        (final_code, remaining_issues, repairs_made)
    """
    issues = check_syntax(code, output_format)

    if not issues:
        return code, [], []

    logger.warning(
        "[validate_output] Found %d syntax issue(s) in %s output",
        len(issues), output_format,
    )

    repairs: list[str] = []
    if auto_repair and output_format in ("pytest", "python_pytest"):
        code, repairs = repair_python_syntax(code)
        if repairs:
            logger.info("[validate_output] Applied %d repair(s)", len(repairs))
            # Re-check after repair
            issues = check_syntax(code, output_format)

    return code, issues, repairs


def _resolve_payload(scenario: TestScenario, endpoint=None) -> dict | None:
    """Resolve the best payload for a scenario from hints and schema."""
    # Start with schema-based payload
    if endpoint and endpoint.request_body:
        payload = fields_to_payload(endpoint.request_body)
    elif scenario.payload_hint:
        payload = dict(scenario.payload_hint)
    else:
        return None

    # Overlay scenario-specific hints
    if scenario.payload_hint:
        for k, v in scenario.payload_hint.items():
            if k.startswith("_"):
                # Handle special directives
                if k == "_omit_field" and v in payload:
                    del payload[v]
            else:
                payload[k] = v

    return payload
