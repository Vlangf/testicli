"""Scan project: detect language, find tests, collect source files."""


from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from testicli.languages.base import detect_language, LanguageSupport
from testicli.models import ProjectConfig

console = Console()

_SKIP_DIRS = {
    ".venv", "venv", "node_modules", ".git", "__pycache__",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", ".next", "coverage", ".eggs", "egg-info",
}

_SUBPROJECT_MARKERS = {"pyproject.toml", "package.json", "go.mod"}


@dataclass
class ScanResult:
    config: ProjectConfig
    language_support: LanguageSupport
    source_files: list[Path]
    test_files: list[Path]


def _find_subprojects(project_root: Path) -> list[Path]:
    """Find subdirectories that contain project markers (monorepo support).

    Returns relative paths to subdirectories containing pyproject.toml,
    package.json, or go.mod. Only looks one level deep.
    """
    subprojects: list[Path] = []
    for child in sorted(project_root.iterdir()):
        if not child.is_dir() or child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        if any((child / marker).exists() for marker in _SUBPROJECT_MARKERS):
            subprojects.append(child.relative_to(project_root))
    return subprojects


def _has_files_with_extension(directory: Path, extensions: list[str]) -> bool:
    """Check if directory contains files with any of the given extensions."""
    for ext in extensions:
        if next(directory.rglob(f"*{ext}"), None) is not None:
            return True
    return False


def _guess_source_dirs(project_root: Path, subprojects: list[Path]) -> list[str]:
    """Guess source directories based on common conventions.

    If standard root-level dirs (src/, lib/, app/) exist and contain source files,
    use them. Otherwise, look inside subprojects.
    """
    candidates = ["src", "lib", "app"]
    found = [d for d in candidates if (project_root / d).is_dir()]

    if found:
        return found

    # Check subprojects for source directories
    if subprojects:
        sub_source_dirs: list[str] = []
        for sub in subprojects:
            for candidate in candidates:
                sub_dir = project_root / sub / candidate
                if sub_dir.is_dir():
                    sub_source_dirs.append(str(sub / candidate))
            # Also check if subproject root itself has source files (flat layout)
            sub_path = project_root / sub
            if _has_files_with_extension(sub_path, [".py", ".js", ".ts", ".go"]):
                # Only add if no candidate subdirs found in this subproject
                if not any(sd.startswith(str(sub)) for sd in sub_source_dirs):
                    sub_source_dirs.append(str(sub))
        if sub_source_dirs:
            return sub_source_dirs

    # Check if there are .py files in root (flat layout)
    if list(project_root.glob("*.py")):
        return ["."]

    return ["src"]


def _guess_test_dirs(project_root: Path, subprojects: list[Path]) -> list[str]:
    """Guess test directories, including in subprojects."""
    candidates = ["tests", "test", "spec"]
    found: list[str] = []

    # Check root level
    for d in candidates:
        if (project_root / d).is_dir():
            found.append(d)

    # Check subprojects
    for sub in subprojects:
        for d in candidates:
            sub_test = project_root / sub / d
            if sub_test.is_dir():
                found.append(str(sub / d))

    return found or ["tests"]


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

    subprojects = _find_subprojects(project_root)
    source_dirs = _guess_source_dirs(project_root, subprojects)
    test_dirs = _guess_test_dirs(project_root, subprojects)

    config = ProjectConfig(
        language=lang_support.language,
        framework=lang_support.framework,
        test_dirs=test_dirs,
        source_dirs=source_dirs,
        project_root=str(project_root),
    )

    source_files = lang_support.find_source_files(project_root, source_dirs)
    test_files = lang_support.find_test_files(project_root, test_dirs)

    console.print(f"  Source dirs: {source_dirs}")
    console.print(f"  Test dirs: {test_dirs}")
    console.print(f"  Source files found: [cyan]{len(source_files)}[/cyan]")
    console.print(f"  Test files found: [cyan]{len(test_files)}[/cyan]")

    return ScanResult(
        config=config,
        language_support=lang_support,
        source_files=source_files,
        test_files=test_files,
    )
