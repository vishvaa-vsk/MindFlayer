"""Validator package — coverage analysis + validation layer."""
from .coverage import validate_coverage
from .pipeline import validate_plan, validate_output
from .models import (
    ValidatedTestPlan,
    ValidatedScenario,
    ValidationReport,
    Precondition,
    DependencyGraph,
    ResourceNode,
    WorkflowEdge,
    StatusModel,
    StatusTransition,
    SyntaxIssue,
    TypeIssue,
    CrudVerb,
)

__all__ = [
    # Coverage
    "validate_coverage",
    # Pipeline
    "validate_plan",
    "validate_output",
    # Models
    "ValidatedTestPlan",
    "ValidatedScenario",
    "ValidationReport",
    "Precondition",
    "DependencyGraph",
    "ResourceNode",
    "WorkflowEdge",
    "StatusModel",
    "StatusTransition",
    "SyntaxIssue",
    "TypeIssue",
    "CrudVerb",
]
