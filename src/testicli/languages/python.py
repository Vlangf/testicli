"""Python language support (pytest / unittest)."""


from pathlib import Path

import pathspec

from testicli.models import Language, TestFramework, TestRunResult


class PythonSupport:
    language = Language.PYTHON
    framework = TestFramework.PYTEST

    def detect(self, project_root: Path) -> bool:
        markers = ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"]
        return any((project_root / m).exists() for m in markers)

    def find_source_files(self, project_root: Path, source_dirs: list[str]) -> list[Path]:
        files: list[Path] = []
        ignore_spec = self._load_gitignore(project_root)
        for src_dir in source_dirs:
            src_path = project_root / src_dir
            if not src_path.exists():
                continue
            for py_file in src_path.rglob("*.py"):
                rel = py_file.relative_to(project_root)
                if ignore_spec and ignore_spec.match_file(str(rel)):
                    continue
                if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                    continue
                files.append(py_file)
        # Also check root-level .py files
        for py_file in project_root.glob("*.py"):
            if not py_file.name.startswith("test_"):
                files.append(py_file)
        return sorted(files)

    def find_test_files(self, project_root: Path, test_dirs: list[str]) -> list[Path]:
        files: list[Path] = []
        for test_dir in test_dirs:
            test_path = project_root / test_dir
            if not test_path.exists():
                continue
            for py_file in test_path.rglob("*.py"):
                if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                    files.append(py_file)
        return sorted(files)

    def test_command(self, test_file: Path, project_root: Path) -> list[str]:
        rel_path = test_file.relative_to(project_root)
        return ["python", "-m", "pytest", str(rel_path), "-v", "--tb=short", "--no-header"]

    def test_file_path(self, source_file: Path, test_dirs: list[str]) -> Path:
        return Path(test_dirs[0]) / f"test_{source_file.stem}.py"

    def parse_test_output(self, output: str, return_code: int) -> TestRunResult:
        return TestRunResult(
            success=return_code == 0,
            output=output,
            return_code=return_code,
            test_file="",
        )

    @staticmethod
    def _load_gitignore(project_root: Path) -> pathspec.PathSpec | None:
        gitignore = project_root / ".gitignore"
        if not gitignore.exists():
            return None
        with open(gitignore) as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
