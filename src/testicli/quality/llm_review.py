"""LLM-based test quality review."""

from testicli.llm.client import LLMClient
from testicli.llm.prompts import (
    QUALITY_REVIEW_PROMPT,
    QUALITY_REVIEW_SYSTEM,
    QUALITY_REVIEW_TOOL_SCHEMA,
)
from testicli.models import QualityIssue, QualityResult, QualitySeverity


def check_llm_quality(
    llm: LLMClient,
    test_code: str,
    source_code: str,
    target_file: str,
    test_name: str,
) -> QualityResult:
    """Use LLM to review test quality beyond static analysis."""
    prompt = QUALITY_REVIEW_PROMPT.format(
        test_code=test_code,
        source_code=source_code,
        target_file=target_file,
        test_name=test_name,
    )

    result = llm.generate_structured(
        system=QUALITY_REVIEW_SYSTEM,
        prompt=prompt,
        tool_name="quality_review",
        tool_schema=QUALITY_REVIEW_TOOL_SCHEMA,
    )

    issues: list[QualityIssue] = []
    for item in result.get("issues", []):
        try:
            severity = QualitySeverity(item["severity"])
        except (ValueError, KeyError):
            severity = QualitySeverity.WARNING
        issues.append(QualityIssue(
            code=item.get("code", "llm_issue"),
            severity=severity,
            message=item.get("message", ""),
            line=item.get("line"),
        ))

    has_errors = any(i.severity == QualitySeverity.ERROR for i in issues)
    return QualityResult(passed=not has_errors, issues=issues, source="llm")
