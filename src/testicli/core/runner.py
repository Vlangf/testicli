"""Execute tests via subprocess and capture output."""


import subprocess
from pathlib import Path

from rich.console import Console

from testicli.languages.base import get_language_support
from testicli.models import Language, ProjectConfig, TestRunResult

console = Console()


def run_test(
    test_file: Path,
    config: ProjectConfig,
    project_root: Path,
    *,
    language: Language | None = None,
    timeout: int = 60,
) -> TestRunResult:
    """Run a single test file and return the result."""
    lang = get_language_support(language or config.language)
    cmd = lang.test_command(test_file, project_root)

    console.print(f"  Running: [dim]{' '.join(cmd)}[/dim]")

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        parsed = lang.parse_test_output(output, result.returncode)
        parsed.test_file = str(test_file)
        return parsed
    except subprocess.TimeoutExpired:
        return TestRunResult(
            success=False,
            output=f"Test timed out after {timeout}s",
            return_code=-1,
            test_file=str(test_file),
        )
    except FileNotFoundError as e:
        return TestRunResult(
            success=False,
            output=f"Command not found: {e}",
            return_code=-1,
            test_file=str(test_file),
        )
