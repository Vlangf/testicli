"""Tests for project scanner."""

from pathlib import Path

from testicli.languages.base import register_language
from testicli.languages.python import PythonSupport
from testicli.core.scanner import scan_project

# Ensure Python is registered
register_language(PythonSupport())


def _setup_python_project(tmp_path: Path) -> None:
    """Create a minimal Python project structure."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "app.py").write_text("def hello(): return 'hi'\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_app.py").write_text("def test_hello(): assert True\n")


def test_scan_detects_python(tmp_path: Path):
    _setup_python_project(tmp_path)
    result = scan_project(tmp_path)

    assert result.config.language.value == "python"
    assert result.config.framework.value == "pytest"


def test_scan_finds_source_files(tmp_path: Path):
    _setup_python_project(tmp_path)
    result = scan_project(tmp_path)

    source_names = [f.name for f in result.source_files]
    assert "app.py" in source_names


def test_scan_finds_test_files(tmp_path: Path):
    _setup_python_project(tmp_path)
    result = scan_project(tmp_path)

    test_names = [f.name for f in result.test_files]
    assert "test_app.py" in test_names


def test_scan_no_language_detected(tmp_path: Path):
    # Empty directory
    import pytest
    with pytest.raises(RuntimeError, match="Could not detect"):
        scan_project(tmp_path)


def test_scan_guesses_test_dir(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "test").mkdir()
    result = scan_project(tmp_path)
    assert result.config.test_dir == "test"
