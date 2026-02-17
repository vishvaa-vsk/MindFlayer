"""AST compile checker — validates generated code syntax.

Format-aware: currently supports Python (pytest), with hooks for
other languages. Runs as post-generation validation to catch
truncated strings, unbalanced brackets, and other LLM artifacts.
"""
from __future__ import annotations

import ast
import re
import logging
from typing import Callable

from validator.models import SyntaxIssue

logger = logging.getLogger(__name__)


# ── Language-specific checkers ────────────────────────────

def check_python_syntax(code: str) -> list[SyntaxIssue]:
    """Parse Python code via AST and return all syntax issues.

    Also detects common LLM artifacts:
    - Truncated strings (unterminated quotes)
    - Unbalanced parentheses / brackets
    - Incomplete function bodies
    """
    issues: list[SyntaxIssue] = []

    # ── Pre-AST heuristic checks ──────────────────────────
    issues.extend(_check_truncated_strings(code))
    issues.extend(_check_unbalanced_delimiters(code))
    issues.extend(_check_incomplete_functions(code))

    # ── AST compile check ─────────────────────────────────
    try:
        ast.parse(code, mode="exec")
    except SyntaxError as e:
        test_name = _find_enclosing_test(code, e.lineno or 0)
        issues.append(SyntaxIssue(
            test_name=test_name,
            line=e.lineno,
            column=e.offset,
            message=str(e.msg),
            severity="error",
        ))

    return issues


def check_json_syntax(code: str) -> list[SyntaxIssue]:
    """Validate JSON syntax (for Postman collections, etc.)."""
    import json as json_mod
    issues: list[SyntaxIssue] = []
    try:
        json_mod.loads(code)
    except json_mod.JSONDecodeError as e:
        issues.append(SyntaxIssue(
            test_name="<json>",
            line=e.lineno,
            column=e.colno,
            message=str(e.msg),
            severity="error",
        ))
    return issues


def check_xml_syntax(code: str) -> list[SyntaxIssue]:
    """Validate XML syntax (for JUnit XML)."""
    import xml.etree.ElementTree as ET
    issues: list[SyntaxIssue] = []
    try:
        ET.fromstring(code)
    except ET.ParseError as e:
        line, col = e.position if hasattr(e, "position") else (None, None)
        issues.append(SyntaxIssue(
            test_name="<xml>",
            line=line,
            column=col,
            message=str(e),
            severity="error",
        ))
    return issues


def check_gherkin_syntax(code: str) -> list[SyntaxIssue]:
    """Basic Gherkin structure validation."""
    issues: list[SyntaxIssue] = []
    lines = code.split("\n")
    has_feature = False
    has_scenario = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("Feature:"):
            has_feature = True
        if stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
            has_scenario = True
    if not has_feature:
        issues.append(SyntaxIssue(
            test_name="<gherkin>", line=1, message="Missing 'Feature:' declaration", severity="error",
        ))
    if not has_scenario:
        issues.append(SyntaxIssue(
            test_name="<gherkin>", line=1, message="No 'Scenario:' blocks found", severity="warning",
        ))
    return issues


# ── Format registry ───────────────────────────────────────

SYNTAX_CHECKERS: dict[str, Callable[[str], list[SyntaxIssue]]] = {
    "pytest": check_python_syntax,
    "python_pytest": check_python_syntax,
    "postman": check_json_syntax,
    "junit": check_xml_syntax,
    "gherkin": check_gherkin_syntax,
    "openapi": lambda code: [],  # YAML validation could be added
}


def check_syntax(code: str, output_format: str = "pytest") -> list[SyntaxIssue]:
    """Check syntax for the given output format.

    Args:
        code: Generated code string
        output_format: One of the supported format keys

    Returns:
        List of SyntaxIssue objects (empty = clean)
    """
    checker = SYNTAX_CHECKERS.get(output_format, lambda _: [])
    return checker(code)


# ── Repair helpers ────────────────────────────────────────

def repair_python_syntax(code: str) -> tuple[str, list[str]]:
    """Attempt to auto-repair common Python syntax issues.

    Returns:
        (repaired_code, list_of_repairs_made)
    """
    repairs: list[str] = []
    lines = code.split("\n")
    repaired_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Repair 1: Truncated string literals
        if _line_has_unterminated_string(line):
            # Find which quote is unterminated
            for q in ['"""', "'''", '"', "'"]:
                count = line.count(q)
                if count % 2 != 0:
                    line = line + q
                    repairs.append(f"Line {i+1}: Closed unterminated string ({q})")
                    break

        # Repair 2: Truncated function body — missing closing of get()/dict literal
        if line.rstrip().endswith(("(", ",")):
            # Check if next line exists and seems like a new function
            if i + 1 < len(lines) and (
                lines[i + 1].strip().startswith("def ") or
                lines[i + 1].strip().startswith("class ") or
                lines[i + 1].strip() == ""
            ):
                # Try to close the expression
                indent = len(line) - len(line.lstrip())
                line = line.rstrip()
                # Count open parens/brackets
                open_parens = line.count("(") - line.count(")")
                open_brackets = line.count("[") - line.count("]")
                open_braces = line.count("{") - line.count("}")
                closing = ")" * open_parens + "]" * open_brackets + "}" * open_braces
                if closing:
                    line = line + closing
                    repairs.append(f"Line {i+1}: Closed unclosed delimiters: {closing}")

        repaired_lines.append(line)
        i += 1

    repaired_code = "\n".join(repaired_lines)

    # Final check: if still broken, try to isolate and remove broken test functions
    try:
        ast.parse(repaired_code, mode="exec")
    except SyntaxError as e:
        repaired_code, removal_repairs = _remove_broken_tests(repaired_code, e)
        repairs.extend(removal_repairs)

    return repaired_code, repairs


def _remove_broken_tests(code: str, initial_error: SyntaxError) -> tuple[str, list[str]]:
    """Remove individual test functions that have syntax errors.

    Iteratively tries to parse, removes broken tests, and retries.
    """
    repairs = []
    lines = code.split("\n")
    max_attempts = 10

    for attempt in range(max_attempts):
        try:
            ast.parse("\n".join(lines), mode="exec")
            break  # Clean!
        except SyntaxError as e:
            error_line = e.lineno or 0
            # Find the enclosing def test_... block
            start, end = _find_test_function_bounds(lines, error_line)
            if start is not None and end is not None:
                removed_name = _extract_test_name_from_def(lines[start])
                del lines[start:end + 1]
                repairs.append(
                    f"Removed broken test '{removed_name}' "
                    f"(lines {start+1}-{end+1}): {e.msg}"
                )
            else:
                # Can't isolate — give up
                repairs.append(f"Could not auto-repair line {error_line}: {e.msg}")
                break

    return "\n".join(lines), repairs


# ── Internal helpers ──────────────────────────────────────

def _check_truncated_strings(code: str) -> list[SyntaxIssue]:
    """Detect unterminated string literals per line."""
    issues = []
    for i, line in enumerate(code.split("\n"), 1):
        if _line_has_unterminated_string(line):
            test_name = _find_enclosing_test(code, i)
            issues.append(SyntaxIssue(
                test_name=test_name,
                line=i,
                message="Unterminated string literal (possible LLM truncation)",
                severity="error",
            ))
    return issues


def _line_has_unterminated_string(line: str) -> bool:
    """Check if a line has an unterminated string literal."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return False
    # Count unescaped quotes (simplified — doesn't handle all edge cases)
    for q in ['"', "'"]:
        # Remove escaped quotes
        clean = stripped.replace(f"\\{q}", "")
        # Remove triple-quoted strings
        for tq in [q * 3]:
            while tq in clean:
                start = clean.index(tq)
                end = clean.find(tq, start + 3)
                if end == -1:
                    # Unterminated triple quote on this line
                    return True
                clean = clean[:start] + clean[end + 3:]
        # Check remaining single quotes
        if clean.count(q) % 2 != 0:
            return True
    return False


def _check_unbalanced_delimiters(code: str) -> list[SyntaxIssue]:
    """Check for unbalanced parentheses, brackets, and braces globally."""
    issues = []
    # Only flag as issue at the end if truly unbalanced across the whole file
    parens = brackets = braces = 0
    for char in code:
        if char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "{":
            braces += 1
        elif char == "}":
            braces -= 1

    if parens != 0:
        issues.append(SyntaxIssue(
            test_name="<global>", message=f"Unbalanced parentheses (net: {parens:+d})", severity="warning",
        ))
    if brackets != 0:
        issues.append(SyntaxIssue(
            test_name="<global>", message=f"Unbalanced brackets (net: {brackets:+d})", severity="warning",
        ))
    if braces != 0:
        issues.append(SyntaxIssue(
            test_name="<global>", message=f"Unbalanced braces (net: {braces:+d})", severity="warning",
        ))
    return issues


def _check_incomplete_functions(code: str) -> list[SyntaxIssue]:
    """Detect test functions that are defined but have no body."""
    issues = []
    lines = code.split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("def test_"):
            # Check if next non-empty line is another def or end of file
            j = i + 1
            has_body = False
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line == "":
                    j += 1
                    continue
                if next_line.startswith("def ") or next_line.startswith("class "):
                    break  # Next function/class without a body
                has_body = True
                break
            if not has_body:
                test_name = _extract_test_name_from_def(line)
                issues.append(SyntaxIssue(
                    test_name=test_name,
                    line=i + 1,
                    message="Test function has no body",
                    severity="error",
                ))
    return issues


def _find_enclosing_test(code: str, line_num: int) -> str:
    """Find the test function name that encloses a given line number."""
    lines = code.split("\n")
    for i in range(min(line_num - 1, len(lines) - 1), -1, -1):
        if lines[i].strip().startswith("def test_"):
            return _extract_test_name_from_def(lines[i])
    return "<unknown>"


def _extract_test_name_from_def(line: str) -> str:
    """Extract test function name from a def line."""
    match = re.match(r"\s*def\s+(test_\w+)", line)
    return match.group(1) if match else "<unknown>"


def _find_test_function_bounds(lines: list[str], error_line: int) -> tuple[int | None, int | None]:
    """Find start and end line indices for the test function enclosing error_line.

    Returns (start_index, end_index) inclusive, or (None, None) if not found.
    """
    # Find start (walk backward to def test_...)
    start = None
    for i in range(min(error_line - 1, len(lines) - 1), -1, -1):
        if lines[i].strip().startswith("def test_"):
            start = i
            break

    if start is None:
        return None, None

    # Find end (next def at same or lower indent, or end of file)
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines) - 1
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped == "":
            continue
        current_indent = len(lines[i]) - len(lines[i].lstrip())
        if current_indent <= base_indent and (
            stripped.startswith("def ") or
            stripped.startswith("class ") or
            stripped.startswith("@") or
            stripped.startswith("# ──")
        ):
            end = i - 1
            # Back up over trailing blank lines
            while end > start and lines[end].strip() == "":
                end -= 1
            break

    return start, end
