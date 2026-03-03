"""CLI entry point for testicli."""


import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from testicli.config import Settings, ensure_agent_dir
from testicli.core.analyzer import analyze_existing_tests
from testicli.core.scanner import scan_project
from testicli.llm.client import LLMClient
from testicli.models import (
    Language,
    ProjectConfig,
    QualitySeverity,
    TestPlan,
    TestRule,
    TestStatus,
    TestType,
)
from testicli.storage.store import Store
from testicli.ui import cat_spinner

# Register language support
from testicli.languages.base import register_language
from testicli.languages.python import PythonSupport
from testicli.languages.javascript import JavaScriptSupport
from testicli.languages.go import GoSupport

register_language(PythonSupport())
register_language(JavaScriptSupport())
register_language(GoSupport())

# Register test type strategies
from testicli.test_types.base import register_test_type
from testicli.test_types.unit import UnitStrategy
from testicli.test_types.integration import IntegrationStrategy
from testicli.test_types.e2e import E2EStrategy
from testicli.test_types.fuzzing import FuzzingStrategy
from testicli.test_types.security import SecurityStrategy

register_test_type(UnitStrategy())
register_test_type(IntegrationStrategy())
register_test_type(E2EStrategy())
register_test_type(FuzzingStrategy())
register_test_type(SecurityStrategy())

app = typer.Typer(name="testicli", help="AI-powered test generator using Claude API")
console = Console()


def _plan_match_key(plan: TestPlan) -> str:
    """Build the full plan filename string for matching."""
    lang_part = f"_{plan.language}" if plan.language else ""
    return f"plan_{plan.test_type.value}{lang_part}.yaml"


def _get_settings() -> Settings:
    if not shutil.which("claude"):
        console.print("[red]Error: 'claude' CLI not found. Install Claude Code and run 'claude login'.[/red]")
        raise typer.Exit(1)
    return Settings.from_env()


# ---------------------------------------------------------------------------
# Reusable helpers — called by both CLI commands and interactive mode
# ---------------------------------------------------------------------------


def _run_init(project_root: Path) -> None:
    """Scan project, save config and rules."""
    if not project_root.exists():
        console.print(f"[red]Error: path {project_root} does not exist[/red]")
        raise typer.Exit(1)

    settings = _get_settings()
    llm = LLMClient(settings)

    result = scan_project(project_root)

    ensure_agent_dir(project_root)
    store = Store(project_root)

    store.save_config(result.config)
    console.print("[green]Saved config.yaml[/green]")

    if result.config.test_dir_info:
        console.print("\n[bold]Discovered test directories:[/bold]")
        for info in result.config.test_dir_info:
            types_str = ", ".join(t.value for t in info.test_types)
            console.print(f"  {info.path} -> [{types_str}]")

    rules = analyze_existing_tests(llm, result.config, result.test_files_by_language)
    store.save_rules(rules)
    console.print("[green]Saved rules.yaml[/green]")

    console.print(f"\n[bold green]Initialized .testicli/ in {project_root}[/bold green]")


def _run_plan_for_type(
    llm: LLMClient,
    store: Store,
    config: ProjectConfig,
    rules: list[TestRule],
    test_type: TestType,
    project_root: Path,
    lang_config: "LanguageConfig | None" = None,
) -> None:
    """Plan tests for a single test type / language combination."""
    from testicli.core.planner import create_plan

    if lang_config is not None:
        lang_configs = [lang_config]
    else:
        lang_configs = config.languages

    for lc in lang_configs:
        existing_plan = store.find_plan(test_type, lc.language.value)
        action = "Updating" if existing_plan else "Creating"
        with cat_spinner(
            f"{action} {test_type.value} test plan for {lc.language.value}..."
        ):
            test_plan = create_plan(
                llm, config, rules, test_type, project_root, lc, existing_plan
            )
        store.save_plan(test_plan)
        console.print(f"[green]Plan saved with {len(test_plan.tests)} tests[/green]")


def _run_write(
    llm: LLMClient,
    store: Store,
    config: ProjectConfig,
    rules: list[TestRule],
    test_plan: TestPlan,
    project_root: Path,
    settings: Settings,
) -> None:
    """Write tests for a given plan."""
    from testicli.core.writer import write_tests

    with cat_spinner(f"Writing tests from plan ({test_plan.test_type.value})..."):
        write_tests(llm, config, rules, test_plan, store, project_root, settings)
    console.print("\n[bold green]Done![/bold green]")


def _run_review(
    store: Store,
    config: ProjectConfig,
    test_plan: TestPlan,
    project_root: Path,
    llm: LLMClient | None,
    llm_review: bool,
    fix: bool,
    max_fix_attempts: int,
) -> None:
    """Review quality of generated tests."""
    from testicli.core.quality import fix_quality_issues, validate_test_quality
    from testicli.core.runner import run_test

    reviewable = [t for t in test_plan.tests if t.status in (TestStatus.PASSED, TestStatus.WEAK) and t.code]
    if not reviewable:
        console.print("[yellow]No passed tests with code to review.[/yellow]")
        return

    console.print(f"\n[blue]Reviewing {len(reviewable)} tests...[/blue]\n")

    run_language: Language | None = None
    if test_plan.language:
        try:
            run_language = Language(test_plan.language)
        except ValueError:
            pass

    results_table = Table(title="Quality Review Results")
    results_table.add_column("Test", style="cyan")
    results_table.add_column("Status", justify="center")
    results_table.add_column("Issues")

    total_issues = 0
    weak_count = 0

    for planned_test in reviewable:
        source_path = project_root / planned_test.target_file
        try:
            source_content = source_path.read_text() if source_path.exists() else ""
        except (OSError, UnicodeDecodeError):
            source_content = ""

        result = validate_test_quality(
            code=planned_test.code,
            language=test_plan.language or config.language.value,
            target_file=planned_test.target_file,
            source_content=source_content,
            test_name=planned_test.name,
            llm_review=llm_review,
            llm=llm,
        )

        error_issues = [i for i in result.issues if i.severity == QualitySeverity.ERROR]
        warn_issues = [i for i in result.issues if i.severity == QualitySeverity.WARNING]
        total_issues += len(result.issues)

        if result.passed:
            status_str = "[green]OK[/green]"
        else:
            status_str = "[red]WEAK[/red]"

        issues_parts = []
        if error_issues:
            issues_parts.append(f"[red]{len(error_issues)} errors[/red]")
        if warn_issues:
            issues_parts.append(f"[yellow]{len(warn_issues)} warnings[/yellow]")
        issues_str = ", ".join(issues_parts) if issues_parts else "[green]none[/green]"

        results_table.add_row(planned_test.name, status_str, issues_str)

        for issue in result.issues:
            sev = "[red]ERROR[/red]" if issue.severity == QualitySeverity.ERROR else "[yellow]WARN[/yellow]"
            line_info = f" (line {issue.line})" if issue.line else ""
            console.print(f"  {sev} [{planned_test.name}] {issue.code}: {issue.message}{line_info}")

        if fix and not result.passed and llm is not None:
            console.print(f"\n  [blue]Attempting to fix {planned_test.name}...[/blue]")
            current_code = planned_test.code
            fixed = False

            for attempt in range(1, max_fix_attempts + 1):
                fixed_code = fix_quality_issues(
                    llm, current_code, result.issues,
                    planned_test.target_file, source_content,
                )

                test_path = project_root / planned_test.output_file
                original_code = current_code
                test_path.write_text(fixed_code)

                run_result = run_test(test_path, config, project_root, language=run_language)
                if not run_result.success:
                    console.print(f"  [yellow]Fix attempt {attempt} broke the test, reverting[/yellow]")
                    test_path.write_text(original_code)
                    continue

                recheck = validate_test_quality(
                    code=fixed_code,
                    language=test_plan.language or config.language.value,
                    target_file=planned_test.target_file,
                    source_content=source_content,
                    test_name=planned_test.name,
                    llm_review=llm_review,
                    llm=llm,
                )

                if recheck.passed:
                    console.print(f"  [green]Fixed on attempt {attempt}![/green]")
                    planned_test.code = fixed_code
                    planned_test.status = TestStatus.PASSED
                    planned_test.quality_issues = []
                    fixed = True
                    break

                current_code = fixed_code
                result = recheck

            if not fixed:
                console.print(f"  [red]Could not fix after {max_fix_attempts} attempts[/red]")
                planned_test.status = TestStatus.WEAK
                planned_test.quality_issues = [i for i in result.issues if i.severity == QualitySeverity.ERROR]
                weak_count += 1
        elif not result.passed:
            planned_test.status = TestStatus.WEAK
            planned_test.quality_issues = [i for i in result.issues if i.severity == QualitySeverity.ERROR]
            weak_count += 1

    console.print()
    console.print(results_table)
    store.update_plan(test_plan)

    if weak_count:
        console.print(f"\n[yellow]{weak_count} test(s) marked as WEAK. Use --fix to attempt auto-repair.[/yellow]")
    elif total_issues == 0:
        console.print("\n[bold green]All tests passed quality checks![/bold green]")
    else:
        console.print(f"\n[green]No critical issues. {total_issues} warning(s) found.[/green]")


def _run_status(store: Store, config: ProjectConfig, project_root: Path) -> None:
    """Display plan/test status overview."""
    console.print(f"[bold]Project:[/bold] {project_root}")
    for lc in config.languages:
        console.print(f"  Language: {lc.language.value}, Framework: {lc.framework.value}")

    rules = store.load_rules()
    console.print(f"  Rules: {len(rules)}")

    plans = store.load_plans()
    if not plans:
        console.print("  Plans: none")
    else:
        table = Table(title="Test Plans")
        table.add_column("Plan")
        table.add_column("Type")
        table.add_column("Tests")
        table.add_column("Passed")
        table.add_column("Failed")
        table.add_column("Weak")
        table.add_column("Pending")

        for p in plans:
            summary = p.summary
            table.add_row(
                f"{p.created_at:%Y-%m-%d %H:%M}",
                p.test_type.value,
                str(len(p.tests)),
                str(summary.get("passed", 0)),
                str(summary.get("failed", 0)),
                str(summary.get("weak", 0)),
                str(summary.get("pending", 0)),
            )
        console.print(table)

    failures = store.load_failures()
    if failures:
        console.print(f"\n  [red]Recorded failures: {len(failures)}[/red]")


def _run_analyze(
    llm: LLMClient,
    store: Store,
    rules: list[TestRule],
    update_rules: bool,
) -> None:
    """Analyze failures and suggest rule improvements."""
    from testicli.core.failure_analyzer import analyze_failures

    failures = store.load_failures()

    if not failures:
        console.print("[yellow]No failures recorded. Nothing to analyze.[/yellow]")
        return

    with cat_spinner(f"Analyzing {len(failures)} failures..."):
        new_rules = analyze_failures(llm, rules, failures)

    if update_rules and new_rules:
        store.save_rules(new_rules)
        console.print(f"[green]Updated rules.yaml with {len(new_rules)} rules[/green]")
    elif new_rules:
        console.print("\n[yellow]Suggested rule changes (use --update-rules to apply):[/yellow]")
        for r in new_rules:
            console.print(f"  [{r.category}] {r.pattern}")


# ---------------------------------------------------------------------------
# CLI commands — thin wrappers around helpers
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """AI-powered test generator using Claude API."""
    if ctx.invoked_subcommand is None:
        from testicli.interactive import run_interactive

        run_interactive()


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project root path"),
) -> None:
    """Scan project, detect language, analyze existing tests."""
    _run_init(path.resolve())


@app.command()
def plan(
    types: str = typer.Option("integration", "-t", "--types", help="Comma-separated test types"),
    path: Path = typer.Argument(Path("."), help="Project root path"),
) -> None:
    """Create test plan for specified types."""
    project_root = path.resolve()
    settings = _get_settings()
    llm = LLMClient(settings)
    store = Store(project_root)

    config = store.load_config()
    if config is None:
        console.print("[red]Error: run 'testicli init' first[/red]")
        raise typer.Exit(1)

    rules = store.load_rules()

    for type_str in types.split(","):
        type_str = type_str.strip()
        try:
            test_type = TestType(type_str)
        except ValueError:
            console.print(f"[red]Unknown test type: {type_str}. Valid: {[t.value for t in TestType]}[/red]")
            continue

        _run_plan_for_type(llm, store, config, rules, test_type, project_root)


@app.command()
def write(
    plan_name: str | None = typer.Option(None, "--plan", help="Specific plan file name"),
    path: Path = typer.Argument(Path("."), help="Project root path"),
) -> None:
    """Write tests from plan: generate, run, fix, run."""
    project_root = path.resolve()
    settings = _get_settings()
    llm = LLMClient(settings)
    store = Store(project_root)

    config = store.load_config()
    if config is None:
        console.print("[red]Error: run 'testicli init' first[/red]")
        raise typer.Exit(1)

    rules = store.load_rules()

    if plan_name:
        plans = store.load_plans()
        matching = [p for p in plans if plan_name in _plan_match_key(p)]
        if not matching:
            console.print(f"[red]No plan matching '{plan_name}' found[/red]")
            raise typer.Exit(1)
        test_plan = matching[0]
    else:
        test_plan = store.load_latest_plan()
        if test_plan is None:
            console.print("[red]No plans found. Run 'testicli plan' first[/red]")
            raise typer.Exit(1)

    _run_write(llm, store, config, rules, test_plan, project_root, settings)


@app.command()
def analyze(
    update_rules: bool = typer.Option(False, "--update-rules", help="Auto-update rules based on analysis"),
    path: Path = typer.Argument(Path("."), help="Project root path"),
) -> None:
    """Analyze failures and suggest rule improvements."""
    project_root = path.resolve()
    settings = _get_settings()
    llm = LLMClient(settings)
    store = Store(project_root)

    rules = store.load_rules()

    _run_analyze(llm, store, rules, update_rules)


@app.command()
def review(
    plan_name: str | None = typer.Option(None, "--plan", help="Specific plan file name"),
    llm_review: bool = typer.Option(False, "--llm-review", help="Enable LLM-based deep review"),
    fix: bool = typer.Option(False, "--fix", help="Attempt to fix quality issues via LLM"),
    max_fix_attempts: int = typer.Option(2, "--max-fix-attempts", help="Max fix attempts per test"),
    path: Path = typer.Argument(Path("."), help="Project root path"),
) -> None:
    """Review quality of generated tests."""
    project_root = path.resolve()
    store = Store(project_root)

    config = store.load_config()
    if config is None:
        console.print("[red]Error: run 'testicli init' first[/red]")
        raise typer.Exit(1)

    llm: LLMClient | None = None
    if llm_review or fix:
        settings = _get_settings()
        llm = LLMClient(settings)

    if plan_name:
        plans = store.load_plans()
        matching = [p for p in plans if plan_name in _plan_match_key(p)]
        if not matching:
            console.print(f"[red]No plan matching '{plan_name}' found[/red]")
            raise typer.Exit(1)
        test_plan = matching[0]
    else:
        test_plan = store.load_latest_plan()
        if test_plan is None:
            console.print("[red]No plans found. Run 'testicli plan' first[/red]")
            raise typer.Exit(1)

    _run_review(store, config, test_plan, project_root, llm, llm_review, fix, max_fix_attempts)


@app.command()
def status(
    path: Path = typer.Argument(Path("."), help="Project root path"),
) -> None:
    """Show plan/test status overview."""
    project_root = path.resolve()
    store = Store(project_root)

    config = store.load_config()
    if config is None:
        console.print("[red]Not initialized. Run 'testicli init' first.[/red]")
        raise typer.Exit(1)

    _run_status(store, config, project_root)


if __name__ == "__main__":
    app()
