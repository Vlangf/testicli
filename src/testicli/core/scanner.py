"""Scan project: detect language, find tests, collect source files."""


from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from testicli.languages.base import detect_language, LanguageSupport
from testicli.models import ProjectConfig

console = Console()


@dataclass
class ScanResult:
    config: ProjectConfig
    language_support: LanguageSupport
    source_files: list[Path]
    test_files: list[Path]


def _guess_source_dirs(project_root: Path) -> list[str]:
    """Guess source directories based on common conventions."""
    candidates = ["src", "lib", "app"]
    found = [d for d in candidates if (project_root / d).is_dir()]
    if not found:
        # Check if there are .py files in root (flat layout)
        if list(project_root.glob("*.py")):
            found = ["."]
    return found or ["src"]


def _guess_test_dir(project_root: Path) -> str:
    """Guess test directory."""
    candidates = ["tests", "test", "spec"]
    for d in candidates:
        if (project_root / d).is_dir():
            return d
    return "tests"


def scan_project(project_root: Path) -> ScanResult:
    """Scan the project directory and detect language, framework, and structure."""
    console.print(f"[blue]Scanning project at {project_root}...[/blue]")

    lang_support = detect_language(project_root)
    if lang_support is None:
        raise RuntimeError(
            "Could not detect project language. "
            "Supported: Python (pyproject.toml/setup.py), JavaScript (package.json), Go (go.mod)"
        )

    console.print(f"  Detected language: [green]{lang_support.language.value}[/green]")
    console.print(f"  Framework: [green]{lang_support.framework.value}[/green]")

    source_dirs = _guess_source_dirs(project_root)
    test_dir = _guess_test_dir(project_root)

    config = ProjectConfig(
        language=lang_support.language,
        framework=lang_support.framework,
        test_dir=test_dir,
        source_dirs=source_dirs,
        project_root=str(project_root),
    )

    source_files = lang_support.find_source_files(project_root, source_dirs)
    test_files = lang_support.find_test_files(project_root, test_dir)

    console.print(f"  Source dirs: {source_dirs}")
    console.print(f"  Test dir: {test_dir}")
    console.print(f"  Source files found: [cyan]{len(source_files)}[/cyan]")
    console.print(f"  Test files found: [cyan]{len(test_files)}[/cyan]")

    return ScanResult(
        config=config,
        language_support=lang_support,
        source_files=source_files,
        test_files=test_files,
    )
