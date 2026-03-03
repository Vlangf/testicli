"""Scan project: detect language, find tests, collect source files."""


import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from testicli.languages.base import detect_all_languages, LanguageSupport
from testicli.models import LanguageConfig, ProjectConfig, TestDirInfo, TestType

console = Console()

_SKIP_DIRS = {
    ".venv", "venv", "node_modules", ".git", "__pycache__",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", ".next", "coverage", ".eggs", "egg-info",
}

_SUBPROJECT_MARKERS = {"pyproject.toml", "package.json", "go.mod"}

_TEST_FILE_PATTERNS = [
    "test_*.py", "*_test.py",                                # Python
    "*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts",     # JS/TS
    "*.test.jsx", "*.spec.jsx", "*.test.tsx", "*.spec.tsx",
    "*_test.go",                                              # Go
]

# Content-based classification patterns: (regex, TestType)
_CONTENT_PATTERNS: list[tuple[str, TestType]] = [
    # Fuzzing
    (r"from hypothesis|import hypothesis", TestType.FUZZING),
    (r"@given\(", TestType.FUZZING),
    (r"import atheris", TestType.FUZZING),
    # E2E
    (r"from selenium|import selenium", TestType.E2E),
    (r"from playwright|import playwright", TestType.E2E),
    (r"import puppeteer|from puppeteer", TestType.E2E),
    (r"cy\.(visit|get|contains)", TestType.E2E),
    (r"@playwright/test", TestType.E2E),
    # Integration
    (r"import supertest|from supertest", TestType.INTEGRATION),
    (r"from fastapi\.testclient|TestClient", TestType.INTEGRATION),
    (r"import httpx|from httpx", TestType.INTEGRATION),
    (r"import requests|from requests", TestType.INTEGRATION),
    (r"testcontainers|import docker", TestType.INTEGRATION),
    (r"net/http/httptest", TestType.INTEGRATION),
    # Security
    (r"import bandit|import safety", TestType.SECURITY),
    (r"DROP TABLE|UNION SELECT|<script>", TestType.SECURITY),
    # Pytest markers
    (r"@pytest\.mark\.integration", TestType.INTEGRATION),
    (r"@pytest\.mark\.e2e", TestType.E2E),
    (r"@pytest\.mark\.security", TestType.SECURITY),
]

# Path segment -> TestType mapping for fallback classification
_PATH_SEGMENT_TYPES: dict[str, TestType] = {
    "unit": TestType.UNIT,
    "integration": TestType.INTEGRATION,
    "e2e": TestType.E2E,
    "fuzzing": TestType.FUZZING,
    "fuzz": TestType.FUZZING,
    "security": TestType.SECURITY,
}


@dataclass
class ScanResult:
    config: ProjectConfig
    language_supports: list[LanguageSupport]
    source_files: list[Path]
    test_files: list[Path]
    test_files_by_language: dict[str, list[Path]]

    @property
    def language_support(self) -> LanguageSupport:
        """Backward compat: return the first language support."""
        return self.language_supports[0]


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


def _guess_test_dirs_by_name(project_root: Path, subprojects: list[Path]) -> list[str]:
    """Guess test directories by conventional names (fallback)."""
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


def _is_test_file(filename: str) -> bool:
    """Check if a filename matches any test file pattern."""
    return any(fnmatch.fnmatch(filename, pat) for pat in _TEST_FILE_PATTERNS)


def _discover_test_dirs(project_root: Path, subprojects: list[Path]) -> list[str]:
    """Discover test directories by scanning for actual test files.

    Walks the file system looking for directories containing test files,
    then collapses to shallowest ancestors. Falls back to name-based
    discovery if no test files are found.
    """
    dirs_with_tests: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Skip hidden dirs and known non-project dirs
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]

        # Check direct children for test file patterns
        if any(_is_test_file(f) for f in filenames):
            rel = os.path.relpath(dirpath, project_root)
            if rel == ".":
                continue  # skip project root itself
            dirs_with_tests.add(rel)

    if not dirs_with_tests:
        return _guess_test_dirs_by_name(project_root, subprojects)

    # Collapse to shallowest ancestors
    sorted_dirs = sorted(dirs_with_tests, key=lambda d: d.count(os.sep))
    result: list[str] = []
    for d in sorted_dirs:
        # Keep only if no existing result is a parent of this dir
        if not any(d.startswith(parent + os.sep) for parent in result):
            result.append(d)

    return result


def _classify_test_file(path: Path) -> set[TestType]:
    """Classify a single test file by analyzing its content.

    Returns at least {UNIT} if no specific signals are found.
    """
    try:
        content = path.read_text(errors="ignore")
    except OSError:
        return {TestType.UNIT}

    found: set[TestType] = set()
    for pattern, test_type in _CONTENT_PATTERNS:
        if re.search(pattern, content):
            found.add(test_type)

    if found:
        return found

    # Fallback: classify by path segments
    parts = path.parts
    for part in parts:
        part_lower = part.lower()
        if part_lower in _PATH_SEGMENT_TYPES:
            found.add(_PATH_SEGMENT_TYPES[part_lower])

    # Default to UNIT if nothing detected
    return found or {TestType.UNIT}


def _classify_test_dir(dir_path: str, project_root: Path) -> list[TestType]:
    """Classify all test files in a directory and return union of types."""
    abs_dir = project_root / dir_path
    found: set[TestType] = set()

    for dirpath, dirnames, filenames in os.walk(abs_dir):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            if _is_test_file(filename):
                file_path = Path(dirpath) / filename
                found |= _classify_test_file(file_path)

    if found:
        return sorted(found, key=lambda t: list(TestType).index(t))

    # Fallback: classify by directory name segments
    for part in Path(dir_path).parts:
        part_lower = part.lower()
        if part_lower in _PATH_SEGMENT_TYPES:
            found.add(_PATH_SEGMENT_TYPES[part_lower])

    if found:
        return sorted(found, key=lambda t: list(TestType).index(t))

    return [TestType.UNIT]


def _build_test_dir_info(
    test_dirs: list[str], project_root: Path,
) -> list[TestDirInfo]:
    """Build TestDirInfo list by combining discovery and classification."""
    return [
        TestDirInfo(path=d, test_types=_classify_test_dir(d, project_root))
        for d in test_dirs
    ]


def scan_project(project_root: Path) -> ScanResult:
    """Scan the project directory and detect language, framework, and structure."""
    console.print(f"[blue]Scanning project at {project_root}...[/blue]")

    subprojects = _find_subprojects(project_root)

    lang_supports = detect_all_languages(
        project_root,
        extra_dirs=[project_root / sub for sub in subprojects],
    )
    if not lang_supports:
        raise RuntimeError(
            "Could not detect project language. "
            "Supported: Python (pyproject.toml/setup.py), JavaScript (package.json), Go (go.mod)"
        )

    for ls in lang_supports:
        console.print(f"  Detected language: [green]{ls.language.value}[/green] ({ls.framework.value})")
    source_dirs = _guess_source_dirs(project_root, subprojects)
    test_dirs = _discover_test_dirs(project_root, subprojects)
    test_dir_info = _build_test_dir_info(test_dirs, project_root)

    languages = [
        LanguageConfig(language=ls.language, framework=ls.framework)
        for ls in lang_supports
    ]

    config = ProjectConfig(
        languages=languages,
        test_dirs=test_dirs,
        test_dir_info=test_dir_info,
        source_dirs=source_dirs,
        project_root=str(project_root),
    )

    # Collect files from all language supports
    source_files: list[Path] = []
    test_files: list[Path] = []
    test_files_by_language: dict[str, list[Path]] = {}
    seen_sources: set[Path] = set()
    seen_tests: set[Path] = set()

    for ls in lang_supports:
        lang_test_files: list[Path] = []
        for f in ls.find_source_files(project_root, source_dirs):
            if f not in seen_sources:
                seen_sources.add(f)
                source_files.append(f)
        for f in ls.find_test_files(project_root, test_dirs):
            if f not in seen_tests:
                seen_tests.add(f)
                test_files.append(f)
            lang_test_files.append(f)
        if lang_test_files:
            test_files_by_language[ls.language.value] = lang_test_files

    console.print(f"  Source dirs: {source_dirs}")
    console.print(f"  Test dirs: {test_dirs}")
    console.print(f"  Source files found: [cyan]{len(source_files)}[/cyan]")
    console.print(f"  Test files found: [cyan]{len(test_files)}[/cyan]")

    return ScanResult(
        config=config,
        language_supports=lang_supports,
        source_files=source_files,
        test_files=test_files,
        test_files_by_language=test_files_by_language,
    )
