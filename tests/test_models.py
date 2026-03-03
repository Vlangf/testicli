"""Tests for Pydantic models."""

from datetime import datetime

from testicli.models import (
    Language,
    LanguageConfig,
    PlannedTest,
    ProjectConfig,
    TestDirInfo,
    TestFailure,
    TestFramework,
    TestPlan,
    TestRule,
    TestRunResult,
    TestStatus,
    TestType,
)


def test_project_config_defaults():
    config = ProjectConfig(
        languages=[LanguageConfig(language=Language.PYTHON, framework=TestFramework.PYTEST)],
    )
    assert config.test_dirs == ["tests"]
    assert config.source_dirs == ["src"]
    assert config.project_root == "."
    # backward compat properties
    assert config.language == Language.PYTHON
    assert config.framework == TestFramework.PYTEST


def test_project_config_custom():
    config = ProjectConfig(
        languages=[LanguageConfig(language=Language.JAVASCRIPT, framework=TestFramework.JEST)],
        test_dirs=["__tests__"],
        source_dirs=["src", "lib"],
        project_root="/my/project",
    )
    assert config.language == Language.JAVASCRIPT
    assert config.test_dirs == ["__tests__"]


def test_project_config_multi_language():
    config = ProjectConfig(
        languages=[
            LanguageConfig(language=Language.PYTHON, framework=TestFramework.PYTEST),
            LanguageConfig(language=Language.JAVASCRIPT, framework=TestFramework.JEST),
        ],
    )
    assert len(config.languages) == 2
    assert config.language == Language.PYTHON  # first
    assert config.framework == TestFramework.PYTEST  # first
    assert config.languages[1].language == Language.JAVASCRIPT
    assert config.languages[1].framework == TestFramework.JEST


def test_test_rule():
    rule = TestRule(category="naming", pattern="test_ prefix", confidence=0.9)
    assert rule.language is None
    assert rule.example == ""
    assert rule.confidence == 0.9


def test_test_rule_with_language():
    rule = TestRule(language="python", category="naming", pattern="test_ prefix", confidence=1.0)
    assert rule.language == "python"
    data = rule.model_dump()
    assert data["language"] == "python"
    restored = TestRule.model_validate(data)
    assert restored.language == "python"
    assert restored == rule


def test_test_rule_language_none_serialization():
    rule = TestRule(category="structure", pattern="one file per module")
    data = rule.model_dump()
    assert data["language"] is None
    restored = TestRule.model_validate(data)
    assert restored.language is None


def test_planned_test_defaults():
    test = PlannedTest(
        id="t1",
        name="test_something",
        description="Tests something",
        test_type=TestType.INTEGRATION,
        target_file="src/app.py",
        output_file="tests/test_app.py",
    )
    assert test.status == TestStatus.PENDING
    assert test.code is None
    assert test.error is None


def test_test_plan_language_field():
    plan = TestPlan(
        name="python_integration_plan",
        test_type=TestType.INTEGRATION,
        language="python",
    )
    assert plan.language == "python"


def test_test_plan_language_none_by_default():
    plan = TestPlan(name="plan", test_type=TestType.INTEGRATION)
    assert plan.language is None


def test_test_plan_language_serialization():
    plan = TestPlan(
        name="python_security_plan",
        test_type=TestType.SECURITY,
        language="python",
    )
    data = plan.model_dump()
    assert data["language"] == "python"
    restored = TestPlan.model_validate(data)
    assert restored.language == "python"


def test_test_plan_summary():
    plan = TestPlan(
        name="my_plan",
        test_type=TestType.INTEGRATION,
        tests=[
            PlannedTest(id="1", name="a", description="a", test_type=TestType.INTEGRATION,
                        target_file="f", output_file="o", status=TestStatus.PASSED),
            PlannedTest(id="2", name="b", description="b", test_type=TestType.INTEGRATION,
                        target_file="f", output_file="o", status=TestStatus.PASSED),
            PlannedTest(id="3", name="c", description="c", test_type=TestType.INTEGRATION,
                        target_file="f", output_file="o", status=TestStatus.FAILED),
            PlannedTest(id="4", name="d", description="d", test_type=TestType.INTEGRATION,
                        target_file="f", output_file="o", status=TestStatus.PENDING),
        ],
    )
    summary = plan.summary
    assert summary == {"passed": 2, "failed": 1, "pending": 1}


def test_test_failure():
    failure = TestFailure(
        test_id="t1",
        test_name="test_something",
        test_code="def test_something(): pass",
        error_output="AssertionError",
    )
    assert failure.attempt == 1
    assert failure.error_type == "unknown"
    assert isinstance(failure.timestamp, datetime)


def test_test_run_result():
    result = TestRunResult(success=True, output="OK", return_code=0, test_file="test.py")
    assert result.success is True


def test_test_type_unit_exists():
    assert TestType.UNIT.value == "unit"
    # UNIT should be the first member
    assert list(TestType)[0] == TestType.UNIT


def test_test_dir_info():
    info = TestDirInfo(path="tests", test_types=[TestType.UNIT, TestType.INTEGRATION])
    assert info.path == "tests"
    assert len(info.test_types) == 2
    assert TestType.UNIT in info.test_types


def test_test_dir_info_defaults():
    info = TestDirInfo(path="tests")
    assert info.test_types == []


def test_test_dir_info_serialization():
    info = TestDirInfo(path="e2e", test_types=[TestType.E2E])
    data = info.model_dump()
    restored = TestDirInfo.model_validate(data)
    assert restored == info


def test_project_config_test_dir_info():
    config = ProjectConfig(
        languages=[LanguageConfig(language=Language.PYTHON, framework=TestFramework.PYTEST)],
        test_dir_info=[
            TestDirInfo(path="tests", test_types=[TestType.UNIT]),
            TestDirInfo(path="e2e", test_types=[TestType.E2E]),
        ],
    )
    assert len(config.test_dir_info) == 2
    assert config.test_dir_info[0].path == "tests"


def test_model_serialization_roundtrip():
    config = ProjectConfig(
        languages=[LanguageConfig(language=Language.PYTHON, framework=TestFramework.PYTEST)],
    )
    data = config.model_dump()
    restored = ProjectConfig.model_validate(data)
    assert restored == config
