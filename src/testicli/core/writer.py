"""Generate test code, run, fix loop."""


import re
from pathlib import Path

from rich.console import Console

from testicli.config import Settings
from testicli.core.runner import run_test
from testicli.llm.client import LLMClient
from testicli.llm.prompts import (
    FIX_TEST_PROMPT,
    FIX_TEST_SYSTEM,
    WRITE_TEST_PROMPT,
    WRITE_TEST_SYSTEM,
)
from testicli.models import (
    PlannedTest,
    ProjectConfig,
    TestFailure,
    TestPlan,
    TestRule,
    TestStatus,
)
from testicli.storage.store import Store
from testicli.test_types.base import get_test_type_strategy

console = Console()


def _strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences if present."""
    code = code.strip()
    if code.startswith("```"):
        # Remove first line (```python or ```)
        lines = code.split("\n")
        lines = lines[1:]
        # Remove last ``` if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code


def _read_source_file(target_file: str, project_root: Path) -> str:
    """Read the source file content for context."""
    path = project_root / target_file
    if not path.exists():
        return "(file not found)"
    try:
        content = path.read_text()
        if len(content) > 50_000:
            content = content[:50_000] + "\n... (truncated)"
        return content
    except (OSError, UnicodeDecodeError):
        return "(could not read file)"


def write_tests(
    llm: LLMClient,
    config: ProjectConfig,
    rules: list[TestRule],
    plan: TestPlan,
    store: Store,
    project_root: Path,
    settings: Settings,
) -> None:
    """Write all tests from a plan with generate-run-fix loop."""
    lang_value = config.language.value
    filtered_rules = [r for r in rules if r.language is None or r.language == lang_value]
    rules_text = "\n".join(f"- [{r.category}] {r.pattern}" for r in filtered_rules) or "No specific rules."

    strategy = get_test_type_strategy(plan.test_type)
    type_additions = strategy.writing_prompt_additions() if strategy else ""

    pending_tests = [t for t in plan.tests if t.status == TestStatus.PENDING]
    total = len(pending_tests)

    for i, planned_test in enumerate(pending_tests, 1):
        console.print(f"\n[bold][{i}/{total}] {planned_test.name}[/bold]")
        planned_test.status = TestStatus.WRITING

        source_content = _read_source_file(planned_test.target_file, project_root)

        # Step 1: Generate test code
        code = _generate_test(
            llm, config, rules_text, type_additions,
            planned_test, source_content,
        )
        code = _strip_markdown_fences(code)

        # Step 2: Write to file
        test_path = project_root / planned_test.output_file
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(code)
        console.print(f"  Wrote: {planned_test.output_file}")

        # Step 3: Run test
        result = run_test(test_path, config, project_root)

        if result.success:
            console.print(f"  [green]PASSED[/green]")
            planned_test.status = TestStatus.PASSED
            planned_test.code = code
            store.update_plan(plan)
            continue

        console.print(f"  [yellow]FAILED (attempt 1)[/yellow]")

        # Step 4: Fix loop
        for attempt in range(2, settings.max_fix_attempts + 1):
            fixed_code = _fix_test(
                llm, code, result.output, planned_test.target_file, source_content,
            )
            fixed_code = _strip_markdown_fences(fixed_code)
            test_path.write_text(fixed_code)
            code = fixed_code

            result = run_test(test_path, config, project_root)
            if result.success:
                console.print(f"  [green]PASSED (attempt {attempt})[/green]")
                planned_test.status = TestStatus.PASSED
                planned_test.code = code
                break

            console.print(f"  [yellow]FAILED (attempt {attempt})[/yellow]")

        if not result.success:
            # Step 5: Save failure, move on
            console.print(f"  [red]FAILED after {settings.max_fix_attempts} attempts[/red]")
            planned_test.status = TestStatus.FAILED
            planned_test.code = code
            planned_test.error = result.output[:2000]

            failure = TestFailure(
                test_id=planned_test.id,
                test_name=planned_test.name,
                test_code=code,
                error_output=result.output[:5000],
                attempt=settings.max_fix_attempts,
            )
            store.save_failure(failure)

        store.update_plan(plan)


def _generate_test(
    llm: LLMClient,
    config: ProjectConfig,
    rules_text: str,
    type_additions: str,
    planned_test: PlannedTest,
    source_content: str,
) -> str:
    prompt = WRITE_TEST_PROMPT.format(
        language=config.language.value,
        framework=config.framework.value,
        rules=rules_text,
        type_specific_additions=type_additions,
        target_file=planned_test.target_file,
        source_content=source_content,
        test_name=planned_test.name,
        test_description=planned_test.description,
    )
    return llm.generate_code(system=WRITE_TEST_SYSTEM, prompt=prompt)


def _fix_test(
    llm: LLMClient,
    test_code: str,
    error_output: str,
    target_file: str,
    source_content: str,
) -> str:
    prompt = FIX_TEST_PROMPT.format(
        test_code=test_code,
        error_output=error_output,
        target_file=target_file,
        source_content=source_content,
    )
    return llm.generate_code(system=FIX_TEST_SYSTEM, prompt=prompt)
