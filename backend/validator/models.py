"""Validation layer models — format-agnostic intermediate representations.

These models capture resource lifecycle, dependency graphs, test ordering,
and precondition metadata. They sit between planning and generation so every
output format (pytest, Postman, JUnit, Gherkin, OpenAPI) benefits.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, field_validator


# ── Resource Lifecycle ────────────────────────────────────

class CrudVerb(str, Enum):
    """Canonical CRUD operations mapped from HTTP methods."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ACTION = "action"   # Non-CRUD, e.g. /approve, /reject

    @classmethod
    def from_http_method(cls, method: str, path: str = "") -> "CrudVerb":
        """Infer CRUD verb from HTTP method + path heuristics."""
        method = method.upper()
        # Sub-resource actions (POST on non-collection paths like /orders/:id/approve)
        if method == "POST" and ":id" in path:
            return cls.ACTION
        mapping = {
            "POST": cls.CREATE,
            "GET": cls.READ,
            "PUT": cls.UPDATE,
            "PATCH": cls.UPDATE,
            "DELETE": cls.DELETE,
        }
        return mapping.get(method, cls.ACTION)


class ResourceNode(BaseModel):
    """A logical API resource extracted from endpoint paths.

    Example: /purchase_orders/:id → resource="purchase_orders"
    """
    name: str                          # e.g. "purchase_orders"
    collection_path: str               # e.g. "/purchase_orders"
    item_path: str | None = None       # e.g. "/purchase_orders/:id"
    endpoints: list[str] = []          # endpoint names that operate on this resource
    crud_map: dict[str, str] = {}      # CrudVerb.value → endpoint_name


class WorkflowEdge(BaseModel):
    """Directed edge in a resource workflow graph.

    Represents "endpoint A must succeed before endpoint B".
    """
    source: str              # endpoint name (e.g. "post__purchase_orders")
    target: str              # endpoint name (e.g. "get__purchase_orders_id")
    resource: str            # resource name they share
    reason: str              # human-readable reason


class DependencyGraph(BaseModel):
    """Complete resource dependency graph for the API."""
    resources: list[ResourceNode] = []
    edges: list[WorkflowEdge] = []
    adjacency: dict[str, list[str]] = {}    # target → [sources it depends on]
    reverse_adj: dict[str, list[str]] = {}  # source → [targets that depend on it]


# ── Status Transitions ────────────────────────────────────

class StatusTransition(BaseModel):
    """A valid state transition for a resource.

    Example: "pending" → "approved" via POST /orders/:id/approve
    """
    resource: str
    from_status: str
    to_status: str
    via_endpoint: str          # endpoint name that triggers this transition
    conditions: list[str] = [] # human-readable conditions


class StatusModel(BaseModel):
    """State machine for a resource's lifecycle."""
    resource: str
    initial_status: str = "created"
    statuses: list[str] = []
    transitions: list[StatusTransition] = []
    terminal_statuses: list[str] = []   # statuses with no outgoing transitions


# ── Test Ordering ─────────────────────────────────────────

class Precondition(BaseModel):
    """A setup action required before a test can execute.

    Format-agnostic: generators translate this into fixture calls,
    Postman pre-request scripts, Gherkin Given steps, etc.
    """
    endpoint_name: str             # endpoint to call for setup
    method: str
    path: str
    payload: dict | None = None
    extract_field: str | None = None  # e.g. "id" → capture from response
    variable_name: str | None = None  # e.g. "order_id" → store as
    description: str = ""


class ValidatedScenario(BaseModel):
    """An enriched test scenario with validation metadata.

    Extends the raw TestScenario with dependency-resolved preconditions,
    proper variable references, and type-checked payloads.
    """
    test_name: str
    endpoint: str
    description: str
    test_type: str
    expected_status: int = 200
    payload_hint: dict | None = None   # Original hint from planning phase (preserved for generator compatibility)
    payload: dict | None = None        # Type-enforced payload (not just hints)
    preconditions: list[Precondition] = []
    variable_refs: dict[str, str] = {} # placeholder → variable_name mapping
    order_priority: int = 0            # lower = run earlier
    group: str = ""                    # resource group for parallel execution
    warnings: list[str] = []           # non-fatal validation issues


class SyntaxIssue(BaseModel):
    """A syntax error found in generated code."""
    test_name: str
    line: int | None = None
    column: int | None = None
    message: str
    severity: str = "error"          # error | warning


class TypeIssue(BaseModel):
    """A type mismatch between payload value and schema."""
    test_name: str
    field_name: str
    expected_type: str
    actual_type: str
    actual_value: str
    suggestion: str = ""


class ValidationReport(BaseModel):
    """Summary of validation findings."""
    total_scenarios: int = 0
    syntax_errors: list[SyntaxIssue] = []
    type_mismatches: list[TypeIssue] = []
    missing_preconditions: int = 0
    reordered_count: int = 0
    injected_preconditions: int = 0
    warnings: list[str] = []

    @property
    def is_clean(self) -> bool:
        return len(self.syntax_errors) == 0 and len(self.type_mismatches) == 0


class ValidatedTestPlan(BaseModel):
    """Fully validated and enriched test plan.

    Consumers (generators) use this instead of raw TestPlan to produce
    higher-quality output across all formats.
    """
    scenarios: list[ValidatedScenario] = []
    dependency_graph: DependencyGraph = DependencyGraph()
    status_models: list[StatusModel] = []
    report: ValidationReport = ValidationReport()
    rationale: str = ""
