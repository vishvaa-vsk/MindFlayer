"""Generated test code models."""
from pydantic import BaseModel, field_validator


class GeneratedTest(BaseModel):
    """A single generated test with code."""
    test_name: str
    test_code: str
    language: str = "python_pytest"
    assertions: list[str] = []

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        valid_languages = {"python_pytest"}
        if v not in valid_languages:
            raise ValueError(f"Invalid language: {v}. Must be one of {valid_languages}")
        return v

    @field_validator("test_code")
    @classmethod
    def validate_test_code_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("test_code cannot be empty")
        return v


class TestSuite(BaseModel):
    """Complete test suite with all generated tests."""
    tests: list[GeneratedTest] = []
    coverage_percentage: float = 0.0

    @field_validator("coverage_percentage")
    @classmethod
    def validate_coverage(cls, v):
        if not 0.0 <= v <= 100.0:
            raise ValueError("coverage_percentage must be between 0 and 100")
        return v
