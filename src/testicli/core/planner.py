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
    LanguageConfig,
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


def _match_test_dir(source_dir: str, test_dirs: list[str]) -> str:
    """Find the test dir sharing the longest common path prefix with source_dir."""
    source_parts = Path(source_dir).parts
    best_match = test_dirs[0]
    best_score = 0
    for td in test_dirs:
        td_parts = Path(td).parts
        common = 0
        for s, t in zip(source_parts, td_parts):
            if s == t:
                common += 1
            else:
                break
        if common > best_score:
            best_score = common
            best_match = td
    return best_match


def _plan_source_dir(
    llm: LLMClient,
    source_dir: str,
    test_dir: str,
    source_files: list[Path],
    project_root: Path,
    lang_config: LanguageConfig,
    rules: list[TestRule],
    test_type: TestType,
    already_planned: set[str] | None = None,
) -> list[PlannedTest]:
    """Plan tests for a single source directory."""
    if already_planned is None:
        already_planned = set()

    # Filter out source files already covered by existing plan
    filtered_files = [
        sf for sf in source_files
        if str(sf.relative_to(project_root)) not in already_planned
    ]
    if not filtered_files:
        return []

    source_contents = []
    total_size = 0
    for sf in filtered_files:
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

    if not source_contents:
        return []

    # Build type-specific context
    strategy = get_test_type_strategy(test_type)
    type_context = ""
    if strategy:
        type_context = (
            strategy.build_planning_context("\n\n".join(source_contents))
            + "\n"
            + strategy.planning_prompt_additions()
        )

    lang_value = lang_config.language.value
    filtered_rules = [r for r in rules if r.language is None or r.language == lang_value]
    rules_text = "\n".join(f"- [{r.category}] {r.pattern}" for r in filtered_rules) or "No specific rules."

    # Build already-covered section for prompt
    if already_planned:
        covered_lines = "\n".join(f"- {f}" for f in sorted(already_planned))
        already_covered_section = (
            f"\nFiles already covered by existing tests (DO NOT plan tests for these):\n"
            f"{covered_lines}\n"
        )
    else:
        already_covered_section = ""

    prompt = PLAN_TESTS_PROMPT.format(
        language=lang_config.language.value,
        framework=lang_config.framework.value,
        test_type=test_type.value,
        test_dir=test_dir,
        type_specific_context=type_context,
        rules=rules_text,
        source_files_content="\n\n".join(source_contents),
        already_covered_section=already_covered_section,
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
    return tests


def create_plan(
    llm: LLMClient,
    config: ProjectConfig,
    rules: list[TestRule],
    test_type: TestType,
    project_root: Path,
    lang_config: LanguageConfig | None = None,
    existing_plan: TestPlan | None = None,
) -> TestPlan:
    """Generate a test plan for the specified type.

    If lang_config is provided, generates a plan for that specific language.
    Otherwise falls back to config.language (first language) for backward compatibility.

    If existing_plan is provided, new tests are appended for uncovered source files
    while existing tests are preserved with their statuses.
    """
    from testicli.languages.base import get_language_support

    if lang_config is None:
        lang_config = config.languages[0]

    lang = get_language_support(lang_config.language)

    # Collect already-planned target files from existing plan
    already_planned: set[str] = set()
    if existing_plan:
        already_planned = {t.target_file for t in existing_plan.tests}

    all_tests: list[PlannedTest] = []

    for source_dir in config.source_dirs:
        source_files = lang.find_source_files(project_root, [source_dir])
        if not source_files:
            continue

        test_dir = _match_test_dir(source_dir, config.test_dirs)

        tests = _plan_source_dir(
            llm=llm,
            source_dir=source_dir,
            test_dir=test_dir,
            source_files=source_files,
            project_root=project_root,
            lang_config=lang_config,
            rules=rules,
            test_type=test_type,
            already_planned=already_planned,
        )
        all_tests.extend(tests)

    # Merge with existing plan if present
    if existing_plan and all_tests:
        # Re-number new test IDs to avoid collisions
        id_offset = len(existing_plan.tests)
        for i, t in enumerate(all_tests):
            t.id = f"test_{id_offset + i + 1:03d}"

        merged_tests = list(existing_plan.tests) + all_tests
        plan = TestPlan(
            name=existing_plan.name,
            test_type=test_type,
            language=lang_config.language.value,
            created_at=existing_plan.created_at,
            tests=merged_tests,
        )
        console.print(
            f"  Updated plan: [green]{len(all_tests)}[/green] new tests"
            f" (total {len(merged_tests)})"
        )
        for t in all_tests:
            console.print(f"    {t.id}: {t.name} -> {t.output_file}")
    elif existing_plan:
        # No new files to plan — return existing plan unchanged
        console.print(f"[yellow]No new source files for {lang_config.language.value}[/yellow]")
        return existing_plan
    else:
        plan = TestPlan(
            name=f"{lang_config.language.value}_{test_type.value}_plan",
            test_type=test_type,
            language=lang_config.language.value,
            tests=all_tests,
        )
        if not all_tests:
            console.print(f"[yellow]No source files found for {lang_config.language.value}[/yellow]")
        else:
            console.print(f"  Created plan with [green]{len(all_tests)}[/green] tests")
            for t in all_tests:
                console.print(f"    {t.id}: {t.name} -> {t.output_file}")

    return plan
