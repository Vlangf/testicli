"""Generate test code via agent mode (tool-based), run, fix loop."""


from pathlib import Path

from claude_agent_sdk import tool
from rich.console import Console

from testicli.config import Settings
from testicli.core.runner import run_test
from testicli.llm.client import LLMClient
from testicli.llm.prompts import (
    FIX_TEST_PROMPT,
    FIX_TEST_SYSTEM_AGENTIC,
    WRITE_TEST_PROMPT,
    WRITE_TEST_SYSTEM_AGENTIC,
)
from testicli.models import (
    Language,
    LanguageConfig,
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


def _resolve_language(plan: TestPlan, config: ProjectConfig) -> tuple[str, str]:
    """Resolve language and framework values from plan, falling back to config."""
    if plan.language:
        for lc in config.languages:
            if lc.language.value == plan.language:
                return lc.language.value, lc.framework.value
        # Plan has a language string but no matching config — use it with first framework
        return plan.language, config.framework.value
    return config.language.value, config.framework.value


def _resolve_language_enum(plan: TestPlan, config: ProjectConfig) -> Language:
    """Resolve Language enum for runner from plan, falling back to config."""
    if plan.language:
        for lc in config.languages:
            if lc.language.value == plan.language:
                return lc.language
    return config.language


def _make_write_file_tool(project_root: Path, result: dict):
    """Create a write_file tool bound to project_root, recording result in `result` dict."""

    @tool("write_file", "Write content to a file", {"file_path": str, "content": str})
    async def write_file(args):
        path = Path(args["file_path"])
        if not path.is_absolute():
            path = project_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"])
        result["written"] = True
        result["path"] = str(path)
        result["content"] = args["content"]
        return {
            "content": [
                {"type": "text", "text": f"Written {len(args['content'])} bytes to {path}"}
            ]
        }

    return write_file


def _generate_test_agentic(
    llm: LLMClient,
    language: str,
    framework: str,
    rules_text: str,
    type_additions: str,
    planned_test: PlannedTest,
    source_content: str,
    project_root: Path,
) -> str | None:
    """Generate a test file via agent mode. Returns file content or None on failure."""
    test_path = project_root / planned_test.output_file
    result: dict = {"written": False}
    write_file = _make_write_file_tool(project_root, result)

    prompt = WRITE_TEST_PROMPT.format(
        language=language,
        framework=framework,
        rules=rules_text,
        type_specific_additions=type_additions,
        target_file=planned_test.target_file,
        source_content=source_content,
        test_name=planned_test.name,
        test_description=planned_test.description,
        output_file=planned_test.output_file,
    )

    llm.generate_with_tools(
        system=WRITE_TEST_SYSTEM_AGENTIC,
        prompt=prompt,
        tools=[write_file],
    )

    if not result["written"] or not test_path.exists():
        return None
    content = test_path.read_text()
    if not content.strip():
        return None
    return content


def _fix_test_agentic(
    llm: LLMClient,
    test_code: str,
    error_output: str,
    planned_test: PlannedTest,
    source_content: str,
    project_root: Path,
) -> str | None:
    """Fix a failing test via agent mode. Returns fixed content or None on failure."""
    test_path = project_root / planned_test.output_file
    result: dict = {"written": False}
    write_file = _make_write_file_tool(project_root, result)

    prompt = FIX_TEST_PROMPT.format(
        test_code=test_code,
        error_output=error_output,
        target_file=planned_test.target_file,
        source_content=source_content,
        output_file=planned_test.output_file,
    )

    llm.generate_with_tools(
        system=FIX_TEST_SYSTEM_AGENTIC,
        prompt=prompt,
        tools=[write_file],
    )

    if not result["written"] or not test_path.exists():
        return None
    content = test_path.read_text()
    if not content.strip():
        return None
    return content


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
    language, framework = _resolve_language(plan, config)
    run_language = _resolve_language_enum(plan, config)

    filtered_rules = [r for r in rules if r.language is None or r.language == language]
    rules_text = (
        "\n".join(f"- [{r.category}] {r.pattern}" for r in filtered_rules)
        or "No specific rules."
    )

    strategy = get_test_type_strategy(plan.test_type)
    type_additions = strategy.writing_prompt_additions() if strategy else ""

    pending_tests = [t for t in plan.tests if t.status == TestStatus.PENDING]
    total = len(pending_tests)

    for i, planned_test in enumerate(pending_tests, 1):
        console.print(f"\n[bold][{i}/{total}] {planned_test.name}[/bold]")
        planned_test.status = TestStatus.WRITING

        source_content = _read_source_file(planned_test.target_file, project_root)

        # Step 1: Generate test code via agent mode
        console.print("  Generating...")
        code = _generate_test_agentic(
            llm, language, framework, rules_text, type_additions,
            planned_test, source_content, project_root,
        )

        if code is None:
            console.print("  [red]FAILED: empty or no file generated[/red]")
            planned_test.status = TestStatus.FAILED
            planned_test.error = "Agent did not produce a test file"
            store.update_plan(plan)
            continue

        console.print(f"  Wrote: {planned_test.output_file}")

        # Step 2: Run test
        test_path = project_root / planned_test.output_file
        result = run_test(test_path, config, project_root, language=run_language)

        if result.success:
            console.print("  [green]PASSED[/green]")
            planned_test.status = TestStatus.PASSED
            planned_test.code = code
            store.update_plan(plan)
            continue

        console.print("  [yellow]FAILED (attempt 1)[/yellow]")

        # Step 3: Fix loop
        for attempt in range(2, settings.max_fix_attempts + 1):
            console.print(f"  Fixing (attempt {attempt})...")
            fixed_code = _fix_test_agentic(
                llm, code, result.output, planned_test, source_content, project_root,
            )

            if fixed_code is None:
                console.print(f"  [yellow]Fix produced empty file (attempt {attempt})[/yellow]")
                continue

            code = fixed_code
            result = run_test(test_path, config, project_root, language=run_language)

            if result.success:
                console.print(f"  [green]PASSED (attempt {attempt})[/green]")
                planned_test.status = TestStatus.PASSED
                planned_test.code = code
                break

            console.print(f"  [yellow]FAILED (attempt {attempt})[/yellow]")

        if not result.success:
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
