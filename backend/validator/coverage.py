"""Coverage validator for dedup and gap analysis."""


def validate_coverage(planned_tests: list[str], existing_tests: list[str]) -> dict:
    """
    Validate coverage and identify gaps.

    Compare planned tests vs existing tests and generate coverage report.

    Args:
        planned_tests: List of test names to generate
        existing_tests: List of test names already implemented

    Returns:
        Coverage report dict with:
        - total_planned: number of tests to generate
        - already_covered: tests in both lists
        - new_tests: tests only in planned
        - duplicates: duplicate tests in planned_tests
        - coverage_improvement: improvement ratio (0-1)
    """
    planned_set = set(planned_tests)
    existing_set = set(existing_tests)

    # Find tests in both lists
    already_covered = list(planned_set & existing_set)

    # Find tests only in planned
    new_tests = list(planned_set - existing_set)

    # Find duplicates within planned_tests
    duplicates = [
        test for test in planned_tests
        if planned_tests.count(test) > 1
    ]
    duplicates = list(set(duplicates))  # Unique list

    # Calculate coverage improvement
    total_planned = len(planned_set)
    coverage_improvement = len(new_tests) / total_planned if total_planned > 0 else 0.0

    return {
        "total_planned": total_planned,
        "already_covered": already_covered,
        "new_tests": new_tests,
        "duplicates": duplicates,
        "coverage_improvement": coverage_improvement,
        "summary": {
            "new": len(new_tests),
            "existing": len(existing_set),
            "total_after_generation": len(existing_set) + len(new_tests),
        }
    }
