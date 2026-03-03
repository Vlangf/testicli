"""Interactive TUI mode for testicli."""

from pathlib import Path

import questionary
from rich.console import Console

from testicli.config import Settings
from testicli.llm.client import LLMClient
from testicli.models import TestPlan, TestStatus, TestType
from testicli.storage.store import Store

console = Console()

BACK = "<- Back"


def _format_plan_choice(plan: TestPlan) -> str:
    """Format a plan for menu display."""
    summary = plan.summary
    parts = []
    for status in ("passed", "pending", "failed", "weak"):
        count = summary.get(status, 0)
        if count > 0:
            parts.append(f"{count} {status}")
    summary_str = ", ".join(parts) if parts else "empty"
    lang = plan.language or "any"
    return f"[{plan.test_type.value} / {lang}] {len(plan.tests)} tests ({summary_str})"


def _show_main_menu() -> str | None:
    return questionary.select(
        "What would you like to do?",
        choices=[
            "Plan tests",
            "Write tests",
            "Review tests",
            "Show status",
            "Analyze failures",
            "Initialize project (re-scan)",
            "Exit",
        ],
    ).ask()


def _show_init_menu() -> str | None:
    return questionary.select(
        "Project not initialized. What would you like to do?",
        choices=[
            "Initialize project",
            "Exit",
        ],
    ).ask()


def _get_settings_interactive() -> Settings | None:
    """Get settings, returning None instead of raising on failure."""
    import shutil

    if not shutil.which("claude"):
        console.print("[red]Error: 'claude' CLI not found. Install Claude Code and run 'claude login'.[/red]")
        return None
    return Settings.from_env()


def _handle_init(project_root: Path) -> None:
    from testicli.cli import _run_init

    _run_init(project_root)


def _handle_plan(store: Store, project_root: Path) -> None:
    from testicli.cli import _run_plan_for_type

    config = store.load_config()
    if config is None:
        console.print("[red]No config found. Initialize first.[/red]")
        return

    plans = store.load_plans()
    rules = store.load_rules()

    # Build choices: existing plans + create new + back
    choices = []
    plan_map: dict[str, TestPlan] = {}
    for p in plans:
        label = f"{_format_plan_choice(p)} -- update"
        choices.append(label)
        plan_map[label] = p

    choices.append("+ Create new plan")
    choices.append(BACK)

    answer = questionary.select(
        "Select a plan to update, or create a new one:",
        choices=choices,
    ).ask()

    if answer is None or answer == BACK:
        return

    settings = _get_settings_interactive()
    if settings is None:
        return
    llm = LLMClient(settings)

    if answer in plan_map:
        # Update existing plan
        selected_plan = plan_map[answer]
        # Find the matching language config
        lang_config = None
        if selected_plan.language:
            for lc in config.languages:
                if lc.language.value == selected_plan.language:
                    lang_config = lc
                    break
        _run_plan_for_type(llm, store, config, rules, selected_plan.test_type, project_root, lang_config)
    else:
        # Create new plan
        # Determine which type/language combos already exist
        existing_combos = {(p.test_type.value, p.language) for p in plans}
        available_types = [t for t in TestType if any(
            (t.value, lc.language.value) not in existing_combos for lc in config.languages
        )]

        if not available_types:
            console.print("[yellow]All test type / language combinations already have plans.[/yellow]")
            return

        type_answer = questionary.select(
            "Select test type:",
            choices=[t.value for t in available_types] + [BACK],
        ).ask()

        if type_answer is None or type_answer == BACK:
            return

        test_type = TestType(type_answer)

        # Language selection
        lang_config = None
        if len(config.languages) > 1:
            available_langs = [
                lc for lc in config.languages
                if (test_type.value, lc.language.value) not in existing_combos
            ]
            lang_choices = [lc.language.value for lc in available_langs]
            lang_choices.append(BACK)

            lang_answer = questionary.select(
                "Select language:",
                choices=lang_choices,
            ).ask()

            if lang_answer is None or lang_answer == BACK:
                return

            for lc in config.languages:
                if lc.language.value == lang_answer:
                    lang_config = lc
                    break

        _run_plan_for_type(llm, store, config, rules, test_type, project_root, lang_config)


def _handle_write(store: Store, project_root: Path) -> None:
    from testicli.cli import _run_write

    config = store.load_config()
    if config is None:
        console.print("[red]No config found. Initialize first.[/red]")
        return

    plans = store.load_plans()
    # Filter to plans with pending tests
    plans_with_pending = [
        p for p in plans
        if any(t.status == TestStatus.PENDING for t in p.tests)
    ]

    if not plans_with_pending:
        console.print("[yellow]No plans with pending tests. Create or update a plan first.[/yellow]")
        return

    choices = []
    plan_map: dict[str, TestPlan] = {}
    for p in plans_with_pending:
        pending_count = sum(1 for t in p.tests if t.status == TestStatus.PENDING)
        lang = p.language or "any"
        label = f"[{p.test_type.value} / {lang}] {pending_count} pending of {len(p.tests)} tests"
        choices.append(label)
        plan_map[label] = p

    choices.append(BACK)

    answer = questionary.select(
        "Select a plan to write tests for:",
        choices=choices,
    ).ask()

    if answer is None or answer == BACK:
        return

    settings = _get_settings_interactive()
    if settings is None:
        return
    llm = LLMClient(settings)
    rules = store.load_rules()

    selected_plan = plan_map[answer]
    _run_write(llm, store, config, rules, selected_plan, project_root, settings)


def _handle_review(store: Store, project_root: Path) -> None:
    from testicli.cli import _run_review

    config = store.load_config()
    if config is None:
        console.print("[red]No config found. Initialize first.[/red]")
        return

    plans = store.load_plans()
    # Filter to plans with reviewable tests (PASSED or WEAK with code)
    plans_with_reviewable = []
    for p in plans:
        reviewable = [t for t in p.tests if t.status in (TestStatus.PASSED, TestStatus.WEAK) and t.code]
        if reviewable:
            plans_with_reviewable.append((p, len(reviewable)))

    if not plans_with_reviewable:
        console.print("[yellow]No plans with reviewable tests.[/yellow]")
        return

    choices = []
    plan_map: dict[str, TestPlan] = {}
    for p, count in plans_with_reviewable:
        lang = p.language or "any"
        label = f"[{p.test_type.value} / {lang}] {count} reviewable tests"
        choices.append(label)
        plan_map[label] = p

    choices.append(BACK)

    answer = questionary.select(
        "Select a plan to review:",
        choices=choices,
    ).ask()

    if answer is None or answer == BACK:
        return

    llm_review = questionary.confirm("Enable LLM-based deep review?", default=False).ask()
    if llm_review is None:
        return

    fix = questionary.confirm("Auto-fix quality issues?", default=False).ask()
    if fix is None:
        return

    llm: LLMClient | None = None
    if llm_review or fix:
        settings = _get_settings_interactive()
        if settings is None:
            return
        llm = LLMClient(settings)

    selected_plan = plan_map[answer]
    _run_review(store, config, selected_plan, project_root, llm, llm_review, fix, max_fix_attempts=2)


def _handle_status(store: Store, project_root: Path) -> None:
    from testicli.cli import _run_status

    config = store.load_config()
    if config is None:
        console.print("[red]No config found. Initialize first.[/red]")
        return

    _run_status(store, config, project_root)


def _handle_analyze(store: Store) -> None:
    from testicli.cli import _run_analyze

    update_rules = questionary.confirm("Auto-update rules based on analysis?", default=False).ask()
    if update_rules is None:
        return

    settings = _get_settings_interactive()
    if settings is None:
        return
    llm = LLMClient(settings)
    rules = store.load_rules()

    _run_analyze(llm, store, rules, update_rules)


def run_interactive() -> None:
    """Main interactive TUI entry point."""
    project_root = Path(".").resolve()
    store = Store(project_root)

    console.print("\n[bold]testicli[/bold] -- AI-powered test generator\n")

    while True:
        try:
            config = store.load_config()
            if config is None:
                action = _show_init_menu()
            else:
                action = _show_main_menu()

            if action is None or action == "Exit":
                break

            try:
                if action == "Initialize project" or action == "Initialize project (re-scan)":
                    _handle_init(project_root)
                elif action == "Plan tests":
                    _handle_plan(store, project_root)
                elif action == "Write tests":
                    _handle_write(store, project_root)
                elif action == "Review tests":
                    _handle_review(store, project_root)
                elif action == "Show status":
                    _handle_status(store, project_root)
                elif action == "Analyze failures":
                    _handle_analyze(store)
            except SystemExit:
                # Catch typer.Exit from helpers to avoid killing the menu loop
                pass

            console.print()  # blank line before next menu

        except KeyboardInterrupt:
            console.print("\n")
            continue
