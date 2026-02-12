"""Test plan models."""
from pydantic import BaseModel, field_validator


# All supported test types
VALID_TEST_TYPES = {
    "positive",           # Happy path — expect success
    "no_auth",            # Missing auth — expect 401
    "dependency_failure", # Skip required setup — expect 404
    "invalid_input",      # Bad ID/params — expect 404
    "state_conflict",     # Violate state constraint — expect 409
    "forbidden_role",     # Wrong role — expect 403
    "field_validation",   # Invalid field format/required — expect 422
    "boundary_value",     # Exceed min/max length — expect 422
    "numeric_boundary",   # Violate numeric min/max (quantity, price) — expect 422
}


class TestScenario(BaseModel):
    """A single test scenario to be generated."""
    test_name: str
    endpoint: str
    description: str
    test_type: str
    expected_status: int = 200     # Expected HTTP response code
    payload_hint: dict | None = None  # Suggested payload for this specific scenario

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, v):
        if v not in VALID_TEST_TYPES:
            raise ValueError(f"Invalid test_type: {v}. Must be one of {VALID_TEST_TYPES}")
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
