"""Test plan models."""
from pydantic import BaseModel, field_validator


class TestScenario(BaseModel):
    """A single test scenario to be generated."""
    test_name: str
    endpoint: str
    description: str
    test_type: str  # positive, no_auth, dependency_failure, invalid_input

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, v):
        valid_types = {"positive", "no_auth", "dependency_failure", "invalid_input"}
        if v not in valid_types:
            raise ValueError(f"Invalid test_type: {v}. Must be one of {valid_types}")
        return v


class TestPlan(BaseModel):
    """Complete test plan with all scenarios."""
    scenarios: list[TestScenario] = []
    rationale: str = ""

    @field_validator("scenarios")
    @classmethod
    def validate_unique_test_names(cls, v):
        names = [s.test_name for s in v]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate test names found in plan")
        return v
