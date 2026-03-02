"""Quality validation orchestrator: static + optional LLM review."""

from testicli.llm.client import LLMClient
from testicli.llm.prompts import FIX_QUALITY_PROMPT, FIX_QUALITY_SYSTEM
from testicli.models import QualityIssue, QualityResult, QualitySeverity
from testicli.quality.llm_review import check_llm_quality
from testicli.quality.static import check_static_quality


def validate_test_quality(
    code: str,
    language: str,
    target_file: str,
    source_content: str,
    test_name: str,
    *,
    llm_review: bool = False,
    llm: LLMClient | None = None,
) -> QualityResult:
    """Run quality checks: static first, then optionally LLM.

    Returns a merged QualityResult combining both sources.
    """
    static_result = check_static_quality(code, language, target_file)

    if not llm_review or llm is None:
        return static_result

    # Only run LLM review if static passed (no point reviewing broken tests)
    if not static_result.passed:
        return static_result

    llm_result = check_llm_quality(llm, code, source_content, target_file, test_name)

    # Merge issues from both sources
    all_issues = static_result.issues + llm_result.issues
    has_errors = any(i.severity == QualitySeverity.ERROR for i in all_issues)
    return QualityResult(
        passed=not has_errors,
        issues=all_issues,
        source="static+llm",
    )


def fix_quality_issues(
    llm: LLMClient,
    code: str,
    issues: list[QualityIssue],
    target_file: str,
    source_content: str,
) -> str:
    """Use LLM to fix quality issues in test code. Returns fixed code."""
    issues_text = "\n".join(
        f"- [{i.severity.value.upper()}] {i.code}: {i.message}"
        + (f" (line {i.line})" if i.line else "")
        for i in issues
    )

    prompt = FIX_QUALITY_PROMPT.format(
        test_code=code,
        target_file=target_file,
        source_content=source_content,
        issues_text=issues_text,
    )

    fixed = llm.generate_code(system=FIX_QUALITY_SYSTEM, prompt=prompt)

    # Strip markdown fences if present
    fixed = fixed.strip()
    if fixed.startswith("```"):
        lines = fixed.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        fixed = "\n".join(lines)

    return fixed
