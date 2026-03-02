"""Analyze existing tests to extract rules via Claude."""


from pathlib import Path

from rich.console import Console

from testicli.llm.client import LLMClient
from testicli.llm.prompts import (
    ANALYZE_TESTS_PROMPT,
    ANALYZE_TESTS_SYSTEM,
    ANALYZE_TESTS_TOOL_SCHEMA,
)
from testicli.models import ProjectConfig, TestRule

console = Console()

MAX_FILE_SIZE = 50_000  # chars per file to send
MAX_TOTAL_CONTENT = 200_000  # total chars to send


def analyze_existing_tests(
    llm: LLMClient,
    config: ProjectConfig,
    test_files: list[Path],
) -> list[TestRule]:
    """Analyze existing test files and extract conventions/rules."""
    if not test_files:
        console.print("[yellow]No existing test files found. Using default rules.[/yellow]")
        return _default_rules(config)

    console.print(f"[blue]Analyzing {len(test_files)} test files...[/blue]")

    # Read test file contents (with size limits)
    test_contents = []
    total_size = 0
    for tf in test_files:
        try:
            content = tf.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > MAX_FILE_SIZE:
            content = content[:MAX_FILE_SIZE] + "\n... (truncated)"
        if total_size + len(content) > MAX_TOTAL_CONTENT:
            break
        test_contents.append(f"--- {tf} ---\n{content}")
        total_size += len(content)

    prompt = ANALYZE_TESTS_PROMPT.format(
        language=config.language.value,
        framework=config.framework.value,
        test_files_content="\n\n".join(test_contents),
    )

    result = llm.generate_structured(
        system=ANALYZE_TESTS_SYSTEM,
        prompt=prompt,
        tool_name="extract_rules",
        tool_schema=ANALYZE_TESTS_TOOL_SCHEMA,
        temperature=0.3,
    )

    rules = [TestRule.model_validate(r) for r in result.get("rules", [])]
    console.print(f"  Extracted [green]{len(rules)}[/green] rules")
    return rules


def _default_rules(config: ProjectConfig) -> list[TestRule]:
    """Return sensible defaults when no existing tests are found."""
    if config.language.value == "python":
        return [
            TestRule(
                category="naming",
                pattern="Test files prefixed with test_, functions prefixed with test_",
                confidence=1.0,
            ),
            TestRule(
                category="structure",
                pattern="One test file per source module",
                confidence=0.8,
            ),
            TestRule(
                category="assertions",
                pattern="Use plain assert statements (pytest style)",
                confidence=0.9,
            ),
        ]
    return []
