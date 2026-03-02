"""Base protocol for language support."""


from pathlib import Path
from typing import Protocol, runtime_checkable

from testicli.models import Language, TestFramework, TestRunResult


@runtime_checkable
class LanguageSupport(Protocol):
    language: Language
    framework: TestFramework

    def detect(self, project_root: Path) -> bool:
        """Return True if this language is detected in the project."""
        ...

    def find_source_files(self, project_root: Path, source_dirs: list[str]) -> list[Path]:
        """Find all source files in the project."""
        ...

    def find_test_files(self, project_root: Path, test_dirs: list[str]) -> list[Path]:
        """Find all existing test files."""
        ...

    def test_command(self, test_file: Path, project_root: Path) -> list[str]:
        """Return the command to run a specific test file."""
        ...

    def test_file_path(self, source_file: Path, test_dirs: list[str]) -> Path:
        """Generate the test file path for a given source file."""
        ...

    def parse_test_output(self, output: str, return_code: int) -> TestRunResult:
        """Parse test runner output into a TestRunResult."""
        ...


# Registry of language support implementations
_registry: dict[Language, LanguageSupport] = {}


def register_language(lang: LanguageSupport) -> None:
    _registry[lang.language] = lang


def get_language_support(language: Language) -> LanguageSupport:
    if language not in _registry:
        raise ValueError(f"No language support registered for {language.value}")
    return _registry[language]


def detect_language(project_root: Path) -> LanguageSupport | None:
    for lang in _registry.values():
        if lang.detect(project_root):
            return lang
    return None


def detect_all_languages(project_root: Path, extra_dirs: list[Path] | None = None) -> list[LanguageSupport]:
    """Return all language supports detected in the project.

    Checks the project root and optionally extra directories (e.g. subprojects).
    """
    found: dict[Language, LanguageSupport] = {}
    dirs_to_check = [project_root] + (extra_dirs or [])
    for d in dirs_to_check:
        for lang in _registry.values():
            if lang.language not in found and lang.detect(d):
                found[lang.language] = lang
    return list(found.values())


def all_languages() -> list[LanguageSupport]:
    return list(_registry.values())
