"""Context models for API requirements parsing."""
from pydantic import BaseModel, field_validator, model_validator


class FieldSpec(BaseModel):
    """Schema field with type, format, and validation constraints.

    Used to describe request/response body fields for an endpoint.
    Drives realistic payload generation and OpenAPI schema output.
    """
    name: str
    field_type: str = "string"      # string, integer, number, boolean, array, object
    format: str | None = None        # email, uri, uuid, date-time, password, phone
    required: bool = True
    example: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    enum: list[str] | None = None
    description: str | None = None

    def to_openapi(self) -> dict:
        """Convert to OpenAPI schema property."""
        prop: dict = {"type": self.field_type}
        if self.format:
            prop["format"] = self.format
        if self.example is not None:
            prop["example"] = self.example
        if self.min_length is not None:
            prop["minLength"] = self.min_length
        if self.max_length is not None:
            prop["maxLength"] = self.max_length
        if self.enum:
            prop["enum"] = self.enum
        if self.description:
            prop["description"] = self.description
        return prop

    def example_value(self) -> str | int | float | bool:
        """Generate a realistic example value for test payloads."""
        if self.example is not None:
            return self.example
        if self.enum:
            return self.enum[0]
        # Format-based defaults
        format_examples = {
            "email": "john@example.com",
            "password": "SecureP@ss123",
            "phone": "+1-555-0123",
            "uri": "https://example.com",
            "url": "https://example.com",
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "date-time": "2025-06-15T10:30:00Z",
            "date": "2025-06-15",
        }
        if self.format and self.format in format_examples:
            return format_examples[self.format]
        # Type-based defaults
        type_examples = {
            "integer": 1,
            "number": 29.99,
            "boolean": True,
        }
        if self.field_type in type_examples:
            return type_examples[self.field_type]
        return f"test_{self.name}"


class StateConstraint(BaseModel):
    """Business rule constraining when an operation is valid.

    Example: "Orders can only be cancelled if status is Pending"
    → field="status", allowed_values=["pending"], error_code=409
    """
    field: str                         # e.g. "status"
    allowed_values: list[str]          # e.g. ["pending"]
    blocked_values: list[str] = []     # e.g. ["shipped", "delivered"]
    description: str                   # Human-readable rule
    error_code: int = 409              # Expected HTTP code on violation


class Endpoint(BaseModel):
    """Represents a single API endpoint with full schema metadata."""
    name: str
    method: str  # GET, POST, PUT, DELETE, etc.
    url_path: str
    requires_auth: bool = False
    depends_on: list[str] = []

    # ── Schema metadata (populated by schema_inference) ──
    request_body: list[FieldSpec] = []
    response_body: list[FieldSpec] = []
    state_constraints: list[StateConstraint] = []
    roles: list[str] = []              # e.g. ["user", "admin"]
    description: str = ""
    expected_success_code: int = 200   # 200 for GET, 201 for POST, etc.

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if v.upper() not in valid_methods:
            raise ValueError(f"Invalid HTTP method: {v}")
        return v.upper()

    @model_validator(mode="after")
    def auto_success_code(self):
        """Auto-set expected success code based on method if not explicitly set."""
        if self.expected_success_code == 200:
            if self.method == "POST":
                self.expected_success_code = 201
            elif self.method == "DELETE":
                self.expected_success_code = 204
        return self


class AuthRule(BaseModel):
    """Authentication rule for endpoints."""
    scope: str  # e.g., "user_auth", "admin_auth"
    required_for: list[str] = []  # List of endpoint names


class SystemContext(BaseModel):
    """Complete system context from API requirements."""
    endpoints: list[Endpoint] = []
    auth_rules: list[AuthRule] = []
    dependencies: dict[str, list[str]] = {}

    @field_validator("endpoints")
    @classmethod
    def validate_no_duplicate_names(cls, v):
        names = [e.name for e in v]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate endpoint names found")
        return v

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies_exist(cls, v, info):
        # Get endpoint names from context
        if "endpoints" in info.data:
            endpoint_names = {e.name for e in info.data["endpoints"]}
            for deps in v.values():
                for dep in deps:
                    if dep not in endpoint_names:
                        raise ValueError(f"Dependency '{dep}' references non-existent endpoint")
        return v
