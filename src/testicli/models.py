"""Pydantic models for testicli."""


from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    GO = "go"


class TestFramework(str, Enum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    VITEST = "vitest"
    GO_TEST = "go_test"


class TestType(str, Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    FUZZING = "fuzzing"
    SECURITY = "security"


class TestDirInfo(BaseModel):
    path: str
    test_types: list["TestType"] = Field(default_factory=list)


class TestStatus(str, Enum):
    PENDING = "pending"
    WRITING = "writing"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WEAK = "weak"


class QualitySeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class QualityIssue(BaseModel):
    code: str
    severity: QualitySeverity
    message: str
    line: int | None = None


class QualityResult(BaseModel):
    passed: bool
    issues: list[QualityIssue] = Field(default_factory=list)
    source: str = "static"


class LanguageConfig(BaseModel):
    language: Language
    framework: TestFramework


class ProjectConfig(BaseModel):
    languages: list[LanguageConfig] = Field(default_factory=list)
    test_dirs: list[str] = Field(default_factory=lambda: ["tests"])
    test_dir_info: list[TestDirInfo] = Field(default_factory=list)
    source_dirs: list[str] = Field(default_factory=lambda: ["src"])
    project_root: str = "."

    @property
    def language(self) -> Language:
        return self.languages[0].language

    @property
    def framework(self) -> TestFramework:
        return self.languages[0].framework


class TestRule(BaseModel):
    language: str | None = None
    category: str
    pattern: str
    example: str = ""
    confidence: float = 0.8


class PlannedTest(BaseModel):
    id: str
    name: str
    description: str
    test_type: TestType
    target_file: str
    output_file: str
    status: TestStatus = TestStatus.PENDING
    code: str | None = None
    error: str | None = None
    quality_issues: list[QualityIssue] = Field(default_factory=list)


class TestPlan(BaseModel):
    name: str
    test_type: TestType
    language: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    tests: list[PlannedTest] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.tests:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        return counts


class TestFailure(BaseModel):
    test_id: str
    test_name: str
    test_code: str
    error_output: str
    error_type: str = "unknown"
    attempt: int = 1
    analysis: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class TestRunResult(BaseModel):
    success: bool
    output: str
    return_code: int
    test_file: str
