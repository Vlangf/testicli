"""Go language support (go test)."""


from pathlib import Path

from testicli.models import Language, TestFramework, TestRunResult


class GoSupport:
    language = Language.GO
    framework = TestFramework.GO_TEST

    def detect(self, project_root: Path) -> bool:
        return (project_root / "go.mod").exists()

    def find_source_files(self, project_root: Path, source_dirs: list[str]) -> list[Path]:
        files: list[Path] = []
        skip_dirs = {"vendor", ".git"}

        search_dirs = [project_root / d for d in source_dirs]
        if not any(d.exists() for d in search_dirs):
            search_dirs = [project_root]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for f in search_dir.rglob("*.go"):
                if any(part in skip_dirs for part in f.parts):
                    continue
                if f.name.endswith("_test.go"):
                    continue
                files.append(f)
        return sorted(files)

    def find_test_files(self, project_root: Path, test_dirs: list[str]) -> list[Path]:
        # Go tests are co-located, so scan whole project
        files: list[Path] = []
        for f in project_root.rglob("*_test.go"):
            if "vendor" not in f.parts:
                files.append(f)
        return sorted(files)

    def test_command(self, test_file: Path, project_root: Path) -> list[str]:
        # Go runs tests by package, not file
        pkg_dir = test_file.parent.relative_to(project_root)
        return ["go", "test", f"./{pkg_dir}/...", "-v", "-run", test_file.stem.replace("_test", "")]

    def test_file_path(self, source_file: Path, test_dirs: list[str]) -> Path:
        # Go tests are co-located
        return source_file.parent / f"{source_file.stem}_test.go"

    def parse_test_output(self, output: str, return_code: int) -> TestRunResult:
        return TestRunResult(
            success=return_code == 0,
            output=output,
            return_code=return_code,
            test_file="",
        )
