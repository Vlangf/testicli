"""Tests for YAML storage."""

from pathlib import Path

from testicli.config import ensure_agent_dir
from testicli.models import (
    Language,
    LanguageConfig,
    PlannedTest,
    ProjectConfig,
    TestFailure,
    TestFramework,
    TestPlan,
    TestRule,
    TestStatus,
    TestType,
)
from testicli.storage.store import Store


def test_save_and_load_config(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    config = ProjectConfig(
        languages=[LanguageConfig(language=Language.PYTHON, framework=TestFramework.PYTEST)],
        test_dirs=["tests"],
        source_dirs=["src"],
    )
    store.save_config(config)

    loaded = store.load_config()
    assert loaded is not None
    assert loaded.language == Language.PYTHON
    assert loaded.framework == TestFramework.PYTEST


def test_load_config_missing(tmp_path: Path):
    store = Store(tmp_path)
    assert store.load_config() is None


def test_save_and_load_rules(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    rules = [
        TestRule(category="naming", pattern="test_ prefix", confidence=0.9),
        TestRule(category="structure", pattern="one file per module", confidence=0.8),
    ]
    store.save_rules(rules)

    loaded = store.load_rules()
    assert len(loaded) == 2
    assert loaded[0].category == "naming"
    assert loaded[1].pattern == "one file per module"


def test_save_and_load_rules_with_language(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    rules = [
        TestRule(language="python", category="naming", pattern="test_ prefix", confidence=0.9),
        TestRule(language="javascript", category="naming", pattern=".test.js suffix", confidence=0.9),
        TestRule(category="general", pattern="universal rule"),
    ]
    store.save_rules(rules)

    loaded = store.load_rules()
    assert len(loaded) == 3
    assert loaded[0].language == "python"
    assert loaded[1].language == "javascript"
    assert loaded[2].language is None


def test_load_rules_empty(tmp_path: Path):
    store = Store(tmp_path)
    assert store.load_rules() == []


def test_save_and_load_plan(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    plan = TestPlan(
        name="integration_plan",
        test_type=TestType.INTEGRATION,
        tests=[
            PlannedTest(
                id="t1",
                name="test_something",
                description="Test it",
                test_type=TestType.INTEGRATION,
                target_file="src/app.py",
                output_file="tests/test_app.py",
            ),
        ],
    )
    store.save_plan(plan)

    plans = store.load_plans()
    assert len(plans) == 1
    assert plans[0].name == "integration_plan"
    assert len(plans[0].tests) == 1


def test_save_and_load_plan_with_language(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    plan = TestPlan(
        name="python_integration_plan",
        test_type=TestType.INTEGRATION,
        language="python",
        tests=[
            PlannedTest(
                id="t1",
                name="test_something",
                description="Test it",
                test_type=TestType.INTEGRATION,
                target_file="src/app.py",
                output_file="tests/test_app.py",
            ),
        ],
    )
    store.save_plan(plan)

    plans = store.load_plans()
    assert len(plans) == 1
    assert plans[0].language == "python"
    assert plans[0].name == "python_integration_plan"


def test_save_multiple_language_plans(tmp_path: Path):
    """Plans for different languages should not overwrite each other."""
    from datetime import datetime

    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    now = datetime.now()
    py_plan = TestPlan(
        name="python_security_plan",
        test_type=TestType.SECURITY,
        language="python",
        created_at=now,
        tests=[],
    )
    js_plan = TestPlan(
        name="javascript_security_plan",
        test_type=TestType.SECURITY,
        language="javascript",
        created_at=now,
        tests=[],
    )
    store.save_plan(py_plan)
    store.save_plan(js_plan)

    plans = store.load_plans()
    assert len(plans) == 2
    languages = {p.language for p in plans}
    assert languages == {"python", "javascript"}


def test_load_latest_plan(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)
    assert store.load_latest_plan() is None

    plan = TestPlan(name="p1", test_type=TestType.E2E, tests=[])
    store.save_plan(plan)
    assert store.load_latest_plan() is not None


def test_save_and_load_failure(tmp_path: Path):
    ensure_agent_dir(tmp_path)
    store = Store(tmp_path)

    failure = TestFailure(
        test_id="t1",
        test_name="test_something",
        test_code="def test(): pass",
        error_output="AssertionError: 1 != 2",
    )
    store.save_failure(failure)

    failures = store.load_failures()
    assert len(failures) == 1
    assert failures[0].test_name == "test_something"
    assert "AssertionError" in failures[0].error_output
