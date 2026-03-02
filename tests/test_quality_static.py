"""Tests for static quality analyzer."""

from testicli.models import QualitySeverity
from testicli.quality.static import check_static_quality


# ---------------------------------------------------------------------------
# Python tests
# ---------------------------------------------------------------------------

class TestPythonEmptyBody:
    def test_pass_only(self):
        code = '''
def test_something():
    pass
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "empty_body" in codes

    def test_ellipsis_only(self):
        code = '''
def test_something():
    ...
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "empty_body" in codes

    def test_docstring_only(self):
        code = '''
def test_something():
    """This test does nothing."""
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "empty_body" in codes

    def test_docstring_and_pass(self):
        code = '''
def test_something():
    """Docs."""
    pass
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "empty_body" in codes


class TestPythonNoAssertions:
    def test_no_assert(self):
        code = '''
def test_something():
    x = 1 + 1
    print(x)
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "no_assertions" in codes

    def test_with_assert_passes(self):
        code = '''
def test_something():
    x = compute()
    assert x == 42
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert "no_assertions" not in [i.code for i in result.issues]

    def test_with_self_assertEqual(self):
        code = '''
import unittest

class TestApp(unittest.TestCase):
    def test_something(self):
        self.assertEqual(compute(), 42)
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert "no_assertions" not in [i.code for i in result.issues]

    def test_with_pytest_raises(self):
        code = '''
import pytest

def test_raises():
    with pytest.raises(ValueError):
        do_bad_thing()
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert "no_assertions" not in [i.code for i in result.issues]


class TestPythonTrivialAssertion:
    def test_assert_true(self):
        code = '''
def test_something():
    assert True
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "trivial_assertion" in codes

    def test_assert_1_eq_1(self):
        code = '''
def test_something():
    assert 1 == 1
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "trivial_assertion" in codes

    def test_real_assertion_not_flagged(self):
        code = '''
def test_something():
    result = compute()
    assert result == 42
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert "trivial_assertion" not in [i.code for i in result.issues]


class TestPythonSwallowedError:
    def test_bare_except_pass(self):
        code = '''
def test_something():
    try:
        do_something()
    except:
        pass
    assert True
'''
        result = check_static_quality(code, "python", "src/app.py")
        codes = [i.code for i in result.issues]
        assert "swallowed_error" in codes
        swallowed = [i for i in result.issues if i.code == "swallowed_error"]
        assert swallowed[0].severity == QualitySeverity.WARNING

    def test_except_exception_pass(self):
        code = '''
def test_something():
    try:
        do_something()
    except Exception:
        pass
    assert True
'''
        result = check_static_quality(code, "python", "src/app.py")
        codes = [i.code for i in result.issues]
        assert "swallowed_error" in codes

    def test_except_with_body_ok(self):
        code = '''
def test_something():
    try:
        do_something()
    except Exception as e:
        assert "expected" in str(e)
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert "swallowed_error" not in [i.code for i in result.issues]


class TestPythonValidTests:
    def test_good_test_passes(self):
        code = '''
import pytest
from mymodule import compute

def test_compute_returns_correct_value():
    result = compute(2, 3)
    assert result == 5

def test_compute_raises_on_invalid():
    with pytest.raises(ValueError):
        compute(-1, 0)
'''
        result = check_static_quality(code, "python", "src/mymodule.py")
        assert result.passed
        error_issues = [i for i in result.issues if i.severity == QualitySeverity.ERROR]
        assert len(error_issues) == 0

    def test_no_test_functions(self):
        code = '''
def helper():
    return 42
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        assert result.issues[0].code == "no_test_functions"


class TestPythonSyntaxError:
    def test_syntax_error(self):
        code = '''
def test_something(
    assert True
'''
        result = check_static_quality(code, "python", "src/app.py")
        assert not result.passed
        assert result.issues[0].code == "syntax_error"


# ---------------------------------------------------------------------------
# JavaScript tests
# ---------------------------------------------------------------------------

class TestJavaScriptChecks:
    def test_no_test_functions(self):
        code = '''
function helper() {
    return 42;
}
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert not result.passed
        assert result.issues[0].code == "no_test_functions"

    def test_empty_test_body(self):
        code = '''
test("should do something", () => {})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "empty_body" in codes

    def test_no_assertions(self):
        code = '''
test("should do something", () => {
    const x = compute();
    console.log(x);
})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "no_assertions" in codes

    def test_trivial_assertion(self):
        code = '''
test("should pass", () => {
    expect(true).toBe(true)
})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "trivial_assertion" in codes

    def test_swallowed_error(self):
        code = '''
test("should handle error", () => {
    try {
        doSomething();
    } catch (e) {}
    expect(1).toBe(1);
})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        codes = [i.code for i in result.issues]
        assert "swallowed_error" in codes

    def test_valid_test(self):
        code = '''
test("should compute correctly", () => {
    const result = compute(2, 3);
    expect(result).toBe(5);
})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert result.passed

    def test_expect_to_throw(self):
        code = '''
test("should throw on bad input", () => {
    expect(() => compute(-1)).toThrow();
})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert "no_assertions" not in [i.code for i in result.issues]

    def test_it_function(self):
        code = '''
it("should work", () => {
    expect(compute()).toBe(42);
})
'''
        result = check_static_quality(code, "javascript", "src/app.js")
        assert result.passed


# ---------------------------------------------------------------------------
# Go tests
# ---------------------------------------------------------------------------

class TestGoChecks:
    def test_no_test_functions(self):
        code = '''
package main

func helper() int {
    return 42
}
'''
        result = check_static_quality(code, "go", "app.go")
        assert not result.passed
        assert result.issues[0].code == "no_test_functions"

    def test_empty_body(self):
        code = '''
package main

import "testing"

func TestSomething(t *testing.T) {}
'''
        result = check_static_quality(code, "go", "app.go")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "empty_body" in codes

    def test_no_assertions(self):
        code = '''
package main

import "testing"

func TestSomething(t *testing.T) {
    x := compute()
    _ = x
}
'''
        result = check_static_quality(code, "go", "app.go")
        assert not result.passed
        codes = [i.code for i in result.issues]
        assert "no_assertions" in codes

    def test_valid_test_with_t_error(self):
        code = '''
package main

import "testing"

func TestCompute(t *testing.T) {
    result := compute(2, 3)
    if result != 5 {
        t.Errorf("expected 5, got %d", result)
    }
}
'''
        result = check_static_quality(code, "go", "app.go")
        assert result.passed

    def test_valid_test_with_t_fatal(self):
        code = '''
package main

import "testing"

func TestCompute(t *testing.T) {
    result := compute(2, 3)
    if result != 5 {
        t.Fatal("unexpected result")
    }
}
'''
        result = check_static_quality(code, "go", "app.go")
        assert result.passed

    def test_valid_test_with_testify(self):
        code = '''
package main

import (
    "testing"
    "github.com/stretchr/testify/assert"
)

func TestCompute(t *testing.T) {
    result := compute(2, 3)
    assert.Equal(t, 5, result)
}
'''
        result = check_static_quality(code, "go", "app.go")
        assert result.passed


# ---------------------------------------------------------------------------
# Unknown language
# ---------------------------------------------------------------------------

class TestUnknownLanguage:
    def test_unknown_language_passes(self):
        result = check_static_quality("anything", "ruby", "app.rb")
        assert result.passed
        assert result.issues == []


# ---------------------------------------------------------------------------
# QualityResult structure
# ---------------------------------------------------------------------------

class TestQualityResultStructure:
    def test_source_is_static(self):
        result = check_static_quality("def test_x():\n    pass", "python", "a.py")
        assert result.source == "static"

    def test_error_severity_marks_not_passed(self):
        code = "def test_x():\n    pass"
        result = check_static_quality(code, "python", "a.py")
        assert not result.passed
        assert any(i.severity == QualitySeverity.ERROR for i in result.issues)
