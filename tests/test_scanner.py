"""Tests for project scanner."""

from pathlib import Path

from testicli.languages.base import register_language
from testicli.languages.javascript import JavaScriptSupport
from testicli.languages.python import PythonSupport
from testicli.core.scanner import (
    scan_project,
    _find_subprojects,
    _guess_source_dirs,
    _guess_test_dirs_by_name,
    _discover_test_dirs,
    _classify_test_file,
    _classify_test_dir,
    _build_test_dir_info,
)
from testicli.models import Language, TestType

# Ensure languages are registered
register_language(PythonSupport())
register_language(JavaScriptSupport())


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
    """Name-based fallback works when no test files exist."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "test").mkdir()
    result = scan_project(tmp_path)
    assert result.config.test_dirs == ["test"]


def test_name_based_fallback(tmp_path: Path):
    """_guess_test_dirs_by_name finds conventional directories."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "spec").mkdir()
    result = _guess_test_dirs_by_name(tmp_path, [])
    assert "tests" in result
    assert "spec" in result


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


def test_multi_language_monorepo(tmp_path: Path):
    """Monorepo with Python and JavaScript detects both languages."""
    # Root marker
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'monorepo'\n")

    # Python subproject
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text("")
    (backend / "app").mkdir()
    (backend / "app" / "main.py").write_text("x = 1\n")
    (backend / "tests").mkdir()
    (backend / "tests" / "test_main.py").write_text("def test_x(): pass\n")

    # JavaScript subproject
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "frontend"}')
    (frontend / "src").mkdir()
    (frontend / "src" / "index.js").write_text("export default 1;\n")

    result = scan_project(tmp_path)

    detected_languages = {lc.language for lc in result.config.languages}
    assert Language.PYTHON in detected_languages
    assert Language.JAVASCRIPT in detected_languages
    assert len(result.config.languages) == 2

    # Backward compat properties still work
    assert result.config.language == Language.PYTHON
    assert result.language_support is not None


def test_test_files_by_language(tmp_path: Path):
    """test_files_by_language maps language to its test files."""
    _setup_python_project(tmp_path)
    result = scan_project(tmp_path)

    assert "python" in result.test_files_by_language
    py_tests = result.test_files_by_language["python"]
    assert len(py_tests) >= 1
    assert any(f.name == "test_app.py" for f in py_tests)


def test_test_files_by_language_monorepo(tmp_path: Path):
    """Monorepo test_files_by_language separates files by language."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'monorepo'\n")

    # Python subproject with tests
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text("")
    (backend / "tests").mkdir()
    (backend / "tests" / "test_main.py").write_text("def test_x(): pass\n")

    # JavaScript subproject with tests
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "frontend"}')
    (frontend / "src").mkdir()
    (frontend / "src" / "index.js").write_text("export default 1;\n")
    (frontend / "tests").mkdir()
    (frontend / "tests" / "index.test.js").write_text("test('x', () => {})\n")

    result = scan_project(tmp_path)

    assert "python" in result.test_files_by_language
    assert "javascript" in result.test_files_by_language

    py_names = [f.name for f in result.test_files_by_language["python"]]
    js_names = [f.name for f in result.test_files_by_language["javascript"]]

    assert "test_main.py" in py_names
    assert "index.test.js" in js_names

    # No cross-contamination
    assert "index.test.js" not in py_names
    assert "test_main.py" not in js_names


# --- Content-based discovery tests ---


def test_content_based_finds_nonstandard_dir(tmp_path: Path):
    """Content-based discovery finds test files in non-standard directories."""
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_validation.py").write_text("def test_ok(): pass\n")

    result = _discover_test_dirs(tmp_path, [])
    assert "checks" in result


def test_content_based_collapses_to_shallowest(tmp_path: Path):
    """Nested test dirs collapse to shallowest ancestor."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_root.py").write_text("def test_root(): pass\n")
    unit = tests / "unit"
    unit.mkdir()
    (unit / "test_unit.py").write_text("def test_unit(): pass\n")

    result = _discover_test_dirs(tmp_path, [])
    assert result == ["tests"]


def test_empty_project_falls_back(tmp_path: Path):
    """Empty project with conventional dir uses name-based fallback."""
    (tmp_path / "tests").mkdir()
    # No test files inside — fallback to name-based
    result = _discover_test_dirs(tmp_path, [])
    assert result == ["tests"]


# --- Type detection tests ---


def test_type_detection_by_imports(tmp_path: Path):
    """Files with specific imports are classified correctly."""
    tests = tmp_path / "tests"
    tests.mkdir()

    fuzz_file = tests / "test_fuzz.py"
    fuzz_file.write_text("from hypothesis import given\n\ndef test_fuzz(): pass\n")

    e2e_file = tests / "test_e2e.py"
    e2e_file.write_text("from playwright.sync_api import sync_playwright\n\ndef test_e2e(): pass\n")

    assert TestType.FUZZING in _classify_test_file(fuzz_file)
    assert TestType.E2E in _classify_test_file(e2e_file)


def test_type_detection_by_markers(tmp_path: Path):
    """Pytest markers are detected for classification."""
    tests = tmp_path / "tests"
    tests.mkdir()

    integ_file = tests / "test_integ.py"
    integ_file.write_text(
        "import pytest\n\n@pytest.mark.integration\ndef test_api(): pass\n"
    )

    result = _classify_test_file(integ_file)
    assert TestType.INTEGRATION in result


def test_type_detection_default_unit(tmp_path: Path):
    """Plain test files with no special imports default to UNIT."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_basic.py").write_text("def test_add(): assert 1 + 1 == 2\n")

    result = _classify_test_dir("tests", tmp_path)
    assert result == [TestType.UNIT]


def test_type_detection_mixed_dir(tmp_path: Path):
    """Directory with mixed test types returns all detected types."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_unit.py").write_text("def test_add(): assert 1 + 1 == 2\n")
    (tests / "test_integ.py").write_text(
        "from fastapi.testclient import TestClient\n\ndef test_api(): pass\n"
    )

    result = _classify_test_dir("tests", tmp_path)
    assert TestType.UNIT in result
    assert TestType.INTEGRATION in result
