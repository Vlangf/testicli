"""Static quality checks for generated tests."""

import ast
import re

from testicli.models import QualityIssue, QualityResult, QualitySeverity


def check_static_quality(code: str, language: str, target_file: str) -> QualityResult:
    """Run static quality checks on test code.

    Returns a QualityResult with issues found. `passed` is True only if
    there are no ERROR-severity issues.
    """
    checkers = {
        "python": _check_python,
        "javascript": _check_javascript,
        "go": _check_go,
    }
    checker = checkers.get(language)
    if checker is None:
        return QualityResult(passed=True, source="static")

    issues = checker(code, target_file)
    has_errors = any(i.severity == QualitySeverity.ERROR for i in issues)
    return QualityResult(passed=not has_errors, issues=issues, source="static")


# ---------------------------------------------------------------------------
# Python (AST-based)
# ---------------------------------------------------------------------------

_PYTHON_ASSERT_PATTERNS = {
    "assert", "assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
    "assertIs", "assertIsNot", "assertIsNone", "assertIsNotNone",
    "assertIn", "assertNotIn", "assertRaises", "assertWarns",
    "assertAlmostEqual", "assertGreater", "assertLess",
    "assertRegex", "assertCountEqual",
}


def _is_test_function(node: ast.FunctionDef) -> bool:
    return node.name.startswith("test_") or node.name.startswith("test")


def _body_is_empty(body: list[ast.stmt]) -> bool:
    """Check if a function body is only pass/Ellipsis/docstring."""
    meaningful = []
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr):
            if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, (str, type(...))):
                continue
        meaningful.append(stmt)
    return len(meaningful) == 0


def _has_assertions(node: ast.FunctionDef) -> bool:
    """Check if a function contains any assertion calls."""
    for child in ast.walk(node):
        # assert statement
        if isinstance(child, ast.Assert):
            return True
        # self.assertXxx() or pytest.raises
        if isinstance(child, ast.Call):
            func = child.func
            # Direct call: e.g. assert_xxx(...)
            if isinstance(func, ast.Name) and func.id in _PYTHON_ASSERT_PATTERNS:
                return True
            # Attribute call: self.assertEqual(), pytest.raises()
            if isinstance(func, ast.Attribute):
                if func.attr in _PYTHON_ASSERT_PATTERNS:
                    return True
                if func.attr == "raises":
                    return True
        # with pytest.raises(...) used as context manager
        if isinstance(child, ast.With):
            for item in child.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute):
                    if ctx.func.attr == "raises":
                        return True
    return False


def _is_trivial_assert(node: ast.Assert) -> bool:
    """Check if an assert is trivially always-true: assert True, assert 1==1."""
    test = node.test
    # assert True / assert 1
    if isinstance(test, ast.Constant) and test.value in (True, 1):
        return True
    # assert 1 == 1
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        if isinstance(test.ops[0], ast.Eq):
            left = test.left
            right = test.comparators[0]
            if (isinstance(left, ast.Constant) and isinstance(right, ast.Constant)
                    and left.value == right.value):
                return True
    return False


def _has_swallowed_errors(node: ast.FunctionDef) -> bool:
    """Check for bare except with pass body."""
    for child in ast.walk(node):
        if isinstance(child, ast.ExceptHandler):
            # bare except or except Exception
            if child.type is None or (
                isinstance(child.type, ast.Name) and child.type.id == "Exception"
            ):
                if _body_is_empty(child.body):
                    return True
    return False


def _has_target_call(node: ast.FunctionDef, target_module: str) -> bool:
    """Check if the test calls anything from the target module."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id != "print":
                return True
            if isinstance(func, ast.Attribute):
                return True
    return False


def _check_python(code: str, target_file: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        issues.append(QualityIssue(
            code="syntax_error", severity=QualitySeverity.ERROR,
            message="Test file has syntax errors",
        ))
        return issues

    target_module = target_file.replace("/", ".").replace(".py", "").split(".")[-1]

    test_functions: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_function(node):
            test_functions.append(node)

    if not test_functions:
        issues.append(QualityIssue(
            code="no_test_functions", severity=QualitySeverity.ERROR,
            message="No test functions found (functions starting with 'test')",
        ))
        return issues

    for func in test_functions:
        line = func.lineno

        if _body_is_empty(func.body):
            issues.append(QualityIssue(
                code="empty_body", severity=QualitySeverity.ERROR,
                message=f"Test '{func.name}' has empty body (only pass/...)",
                line=line,
            ))
            continue

        if not _has_assertions(func):
            issues.append(QualityIssue(
                code="no_assertions", severity=QualitySeverity.ERROR,
                message=f"Test '{func.name}' has no assertions",
                line=line,
            ))

        # Check for trivial assertions
        for child in ast.walk(func):
            if isinstance(child, ast.Assert) and _is_trivial_assert(child):
                issues.append(QualityIssue(
                    code="trivial_assertion", severity=QualitySeverity.ERROR,
                    message=f"Test '{func.name}' has trivial assertion (assert True / assert 1==1)",
                    line=child.lineno,
                ))

        if _has_swallowed_errors(func):
            issues.append(QualityIssue(
                code="swallowed_error", severity=QualitySeverity.WARNING,
                message=f"Test '{func.name}' has bare except with pass (swallowed error)",
                line=line,
            ))

        if not _has_target_call(func, target_module):
            issues.append(QualityIssue(
                code="no_target_call", severity=QualitySeverity.WARNING,
                message=f"Test '{func.name}' does not call any functions from target module",
                line=line,
            ))

    return issues


# ---------------------------------------------------------------------------
# JavaScript (regex-based)
# ---------------------------------------------------------------------------

def _check_javascript(code: str, target_file: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []

    # Check for test/it functions
    test_blocks = re.findall(r'\b(?:test|it)\s*\(', code)
    if not test_blocks:
        issues.append(QualityIssue(
            code="no_test_functions", severity=QualitySeverity.ERROR,
            message="No test()/it() calls found",
        ))
        return issues

    # Check for empty test bodies: test("name", () => {})  or  test("name", function() {})
    empty_body = re.findall(
        r'\b(?:test|it)\s*\([^,]+,\s*(?:async\s+)?(?:\(\)\s*=>|function\s*\(\))\s*\{\s*\}',
        code,
    )
    if empty_body:
        issues.append(QualityIssue(
            code="empty_body", severity=QualitySeverity.ERROR,
            message="Found test(s) with empty body",
        ))

    # Check for assertions
    has_expect = bool(re.search(r'\bexpect\s*\(', code))
    has_assert = bool(re.search(r'\bassert[\.\(]', code))
    has_throw = bool(re.search(r'\.toThrow\s*\(', code))
    if not has_expect and not has_assert and not has_throw:
        issues.append(QualityIssue(
            code="no_assertions", severity=QualitySeverity.ERROR,
            message="No expect()/assert calls found in tests",
        ))

    # Trivial assertions
    trivial = re.findall(r'expect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)', code, re.IGNORECASE)
    if trivial:
        issues.append(QualityIssue(
            code="trivial_assertion", severity=QualitySeverity.ERROR,
            message="Found trivial assertion: expect(true).toBe(true)",
        ))

    # Swallowed errors: empty catch blocks
    swallowed = re.findall(r'catch\s*\([^)]*\)\s*\{\s*\}', code)
    if swallowed:
        issues.append(QualityIssue(
            code="swallowed_error", severity=QualitySeverity.WARNING,
            message="Found empty catch {} block (swallowed error)",
        ))

    return issues


# ---------------------------------------------------------------------------
# Go (regex-based)
# ---------------------------------------------------------------------------

def _check_go(code: str, target_file: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []

    # Check for test functions
    test_funcs = re.findall(r'func\s+(Test\w+)\s*\(\s*\w+\s+\*testing\.T\s*\)', code)
    if not test_funcs:
        issues.append(QualityIssue(
            code="no_test_functions", severity=QualitySeverity.ERROR,
            message="No func TestXxx(t *testing.T) functions found",
        ))
        return issues

    # Check for empty function bodies (very basic: func Test...(...) {\n})
    empty_bodies = re.findall(
        r'func\s+Test\w+\s*\([^)]*\)\s*\{\s*\}',
        code,
    )
    if empty_bodies:
        issues.append(QualityIssue(
            code="empty_body", severity=QualitySeverity.ERROR,
            message="Found test function(s) with empty body",
        ))

    # Check for assertions (t.Error, t.Errorf, t.Fatal, t.Fatalf, t.Fail)
    has_assertions = bool(re.search(
        r'\bt\.\s*(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow|Log|Logf)\s*\(',
        code,
    ))
    # Also check for testify or similar
    has_testify = bool(re.search(r'\b(?:assert|require)\s*\.', code))
    if not has_assertions and not has_testify:
        issues.append(QualityIssue(
            code="no_assertions", severity=QualitySeverity.ERROR,
            message="No t.Error/t.Fatal/assert calls found in tests",
        ))

    return issues
