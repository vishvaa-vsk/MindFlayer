"""Context models for API requirements parsing."""
from pydantic import BaseModel, field_validator


class Endpoint(BaseModel):
    """Represents a single API endpoint."""
    name: str
    method: str  # GET, POST, PUT, DELETE, etc.
    url_path: str
    requires_auth: bool = False
    depends_on: list[str] = []

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if v.upper() not in valid_methods:
            raise ValueError(f"Invalid HTTP method: {v}")
        return v.upper()


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
