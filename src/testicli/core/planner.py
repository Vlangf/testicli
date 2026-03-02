"""Generate test plans via Claude."""


from pathlib import Path

from rich.console import Console

from testicli.llm.client import LLMClient
from testicli.llm.prompts import (
    PLAN_TESTS_PROMPT,
    PLAN_TESTS_SYSTEM,
    PLAN_TESTS_TOOL_SCHEMA,
)
from testicli.models import (
    PlannedTest,
    ProjectConfig,
    TestPlan,
    TestRule,
    TestType,
)
from testicli.test_types.base import get_test_type_strategy

console = Console()

MAX_FILE_SIZE = 30_000
MAX_TOTAL_CONTENT = 150_000


def create_plan(
    llm: LLMClient,
    config: ProjectConfig,
    rules: list[TestRule],
    test_type: TestType,
    project_root: Path,
) -> TestPlan:
    """Generate a test plan for the specified type."""
    from testicli.languages.base import get_language_support

    lang = get_language_support(config.language)
    source_files = lang.find_source_files(project_root, config.source_dirs)

    if not source_files:
        console.print("[yellow]No source files found[/yellow]")
        return TestPlan(name=f"{test_type.value}_plan", test_type=test_type)

    # Read source files
    source_contents = []
    total_size = 0
    for sf in source_files:
        try:
            content = sf.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        rel = sf.relative_to(project_root)
        if len(content) > MAX_FILE_SIZE:
            content = content[:MAX_FILE_SIZE] + "\n... (truncated)"
        if total_size + len(content) > MAX_TOTAL_CONTENT:
            break
        source_contents.append(f"--- {rel} ---\n{content}")
        total_size += len(content)

    # Build type-specific context
    strategy = get_test_type_strategy(test_type)
    type_context = ""
    if strategy:
        type_context = (
            strategy.build_planning_context("\n\n".join(source_contents))
            + "\n"
            + strategy.planning_prompt_additions()
        )

    rules_text = "\n".join(f"- [{r.category}] {r.pattern}" for r in rules) or "No specific rules."

    prompt = PLAN_TESTS_PROMPT.format(
        language=config.language.value,
        framework=config.framework.value,
        test_type=test_type.value,
        type_specific_context=type_context,
        rules=rules_text,
        source_files_content="\n\n".join(source_contents),
    )

    result = llm.generate_structured(
        system=PLAN_TESTS_SYSTEM,
        prompt=prompt,
        tool_name="create_plan",
        tool_schema=PLAN_TESTS_TOOL_SCHEMA,
        temperature=0.3,
    )

    tests = []
    for t in result.get("tests", []):
        tests.append(
            PlannedTest(
                id=t["id"],
                name=t["name"],
                description=t["description"],
                test_type=test_type,
                target_file=t["target_file"],
                output_file=t["output_file"],
            )
        )

    plan = TestPlan(
        name=f"{test_type.value}_plan",
        test_type=test_type,
        tests=tests,
    )

    console.print(f"  Created plan with [green]{len(tests)}[/green] tests")
    for t in tests:
        console.print(f"    {t.id}: {t.name} -> {t.output_file}")

    return plan
