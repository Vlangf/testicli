"""JavaScript/TypeScript language support (jest / vitest)."""


from pathlib import Path

from testicli.models import Language, TestFramework, TestRunResult


class JavaScriptSupport:
    language = Language.JAVASCRIPT
    framework = TestFramework.JEST

    def detect(self, project_root: Path) -> bool:
        return (project_root / "package.json").exists()

    def find_source_files(self, project_root: Path, source_dirs: list[str]) -> list[Path]:
        extensions = ("*.js", "*.ts", "*.jsx", "*.tsx")
        skip_dirs = {"node_modules", "dist", "build", ".next", "coverage"}
        files: list[Path] = []

        for src_dir in source_dirs:
            src_path = project_root / src_dir
            if not src_path.exists():
                continue
            for ext in extensions:
                for f in src_path.rglob(ext):
                    if any(part in skip_dirs for part in f.parts):
                        continue
                    if ".test." in f.name or ".spec." in f.name or f.name.startswith("test"):
                        continue
                    files.append(f)
        return sorted(files)

    def find_test_files(self, project_root: Path, test_dirs: list[str]) -> list[Path]:
        extensions = ("*.test.js", "*.test.ts", "*.spec.js", "*.spec.ts",
                       "*.test.jsx", "*.test.tsx", "*.spec.jsx", "*.spec.tsx")
        files: list[Path] = []
        searched: set[Path] = set()

        for test_dir in test_dirs:
            test_path = project_root / test_dir
            if not test_path.exists() or test_path in searched:
                continue
            searched.add(test_path)
            for ext in extensions:
                files.extend(test_path.rglob(ext))

        # Fallback: check for co-located test files in src/
        if not files:
            src_path = project_root / "src"
            if src_path.exists() and src_path not in searched:
                for ext in extensions:
                    files.extend(src_path.rglob(ext))

        return sorted(files)

    def test_command(self, test_file: Path, project_root: Path) -> list[str]:
        rel_path = test_file.relative_to(project_root)
        # Detect vitest vs jest
        if (project_root / "vitest.config.ts").exists() or (project_root / "vitest.config.js").exists():
            return ["npx", "vitest", "run", str(rel_path)]
        return ["npx", "jest", str(rel_path), "--no-coverage"]

    def test_file_path(self, source_file: Path, test_dirs: list[str]) -> Path:
        stem = source_file.stem
        suffix = source_file.suffix
        return Path(test_dirs[0]) / f"{stem}.test{suffix}"

    def parse_test_output(self, output: str, return_code: int) -> TestRunResult:
        return TestRunResult(
            success=return_code == 0,
            output=output,
            return_code=return_code,
            test_file="",
        )
