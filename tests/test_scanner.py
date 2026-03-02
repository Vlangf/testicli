"""Tests for project scanner."""

from pathlib import Path

from testicli.languages.base import register_language
from testicli.languages.python import PythonSupport
from testicli.core.scanner import scan_project, _find_subprojects, _guess_source_dirs, _guess_test_dirs

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


def test_scan_guesses_test_dirs(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "test").mkdir()
    result = scan_project(tmp_path)
    assert result.config.test_dirs == ["test"]


def test_find_subprojects(tmp_path: Path):
    """Subprojects with project markers are detected."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "pyproject.toml").write_text("")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}")
    (tmp_path / "docs").mkdir()  # no marker — not a subproject

    subs = _find_subprojects(tmp_path)
    sub_names = [str(s) for s in subs]
    assert "backend" in sub_names
    assert "frontend" in sub_names
    assert "docs" not in sub_names


def test_find_subprojects_skips_hidden_and_venv(tmp_path: Path):
    """Hidden dirs and venv are skipped."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "package.json").write_text("{}")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyproject.toml").write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.json").write_text("{}")

    assert _find_subprojects(tmp_path) == []


def test_monorepo_source_and_test_dirs(tmp_path: Path):
    """Monorepo with subprojects finds source and test dirs correctly."""
    # Root marker
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'monorepo'\n")

    # backend subproject
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text("")
    (backend / "app").mkdir()
    (backend / "app" / "main.py").write_text("x = 1\n")
    (backend / "tests").mkdir()
    (backend / "tests" / "test_main.py").write_text("def test_x(): pass\n")

    # frontend subproject
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}")
    (frontend / "src").mkdir()
    (frontend / "src" / "index.ts").write_text("")

    result = scan_project(tmp_path)

    assert "backend/app" in result.config.source_dirs
    assert "frontend/src" in result.config.source_dirs
    assert "backend/tests" in result.config.test_dirs

    # Should find source and test files from subprojects
    source_names = [f.name for f in result.source_files]
    assert "main.py" in source_names

    test_names = [f.name for f in result.test_files]
    assert "test_main.py" in test_names
