# testicli

AI test agent powered by Claude — scans your project, learns conventions from existing tests, generates integration/e2e/fuzzing/security tests, runs them, and auto-fixes failures. Supports Python, JavaScript, and Go.

## Features

- **Auto-detection** — detects language (Python, JavaScript, Go), framework (pytest, jest, vitest, go test), project structure
- **Learns from your code** — analyzes existing tests, extracts naming conventions, assertion styles, mocking patterns
- **Multiple test types** — integration, e2e, fuzzing (property-based), security
- **Self-healing** — runs generated tests, auto-fixes failures, retries
- **Failure analysis** — analyzes recurring failures, suggests improvements to test rules

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Anthropic API key

## Installation

```bash
git clone <repo-url>
cd testicli
uv sync
```

Or install as a tool:

```bash
uv tool install .
```

## Configuration

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Optional environment variables:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Your Anthropic API key |
| `TEST_AGENT_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `TEST_AGENT_MAX_FIX_ATTEMPTS` | `2` | Max attempts to fix a failing test |

## Usage

### 1. Initialize on your project

```bash
uv run testicli init /path/to/your/project
```

This will:
- Detect the language and test framework
- Find source files and existing tests
- Analyze existing tests to extract conventions and rules
- Create `.testicli/` directory with `config.yaml` and `rules.yaml`

Example output:
```
Scanning project at /path/to/your/project...
  Detected language: python
  Framework: pytest
  Source dirs: ['src']
  Test dir: tests
  Source files found: 12
  Test files found: 5
  Analyzing 5 test files...
  Extracted 8 rules
Saved config.yaml
Saved rules.yaml

Initialized .testicli/ in /path/to/your/project
```

### 2. Create a test plan

```bash
# Single type
uv run testicli plan -t integration /path/to/your/project

# Multiple types
uv run testicli plan -t integration,e2e,security /path/to/your/project
```

Available test types: `integration`, `e2e`, `fuzzing`, `security`

This sends your source code and extracted rules to Claude, which creates a list of planned tests. Plans are saved to `.testicli/plans/`.

### 3. Write tests

```bash
# Write tests from the latest plan
uv run testicli write /path/to/your/project

# Write tests from a specific plan
uv run testicli write --plan 20260301 /path/to/your/project
```

For each planned test, the tool:
1. Generates test code via Claude API
2. Writes the code to the output file
3. Runs the test
4. If it fails — sends the error back to Claude for a fix, rewrites, reruns
5. If it fails again — saves the failure to `.testicli/failures/`, moves on
6. Updates the plan status (passed/failed)

### 4. Review test quality

```bash
# Static analysis only (free, no API calls)
uv run testicli review /path/to/your/project

# With LLM-based deep review
uv run testicli review --llm-review /path/to/your/project

# Auto-fix weak tests
uv run testicli review --fix /path/to/your/project

# Review a specific plan
uv run testicli review --plan 20260301 /path/to/your/project
```

Checks passed tests for quality issues:
- **Static analysis** (always) — detects empty bodies (`pass`), missing assertions, trivial assertions (`assert True`), swallowed errors (`except: pass`)
- **LLM review** (with `--llm-review`) — deeper analysis of test meaningfulness, edge case coverage, correct mocking

Tests with critical issues are marked as `WEAK` in the plan. Use `--fix` to attempt automatic repair via LLM (reverts if the fix breaks the test).

### 5. Analyze failures

```bash
# View suggestions
uv run testicli analyze /path/to/your/project

# Auto-update rules based on failure analysis
uv run testicli analyze --update-rules /path/to/your/project
```

Analyzes recorded failures, identifies patterns, and suggests improvements to your test-writing rules.

### 6. Check status

```bash
uv run testicli status /path/to/your/project
```

Shows an overview: project config, number of rules, plans with pass/fail/weak/pending counts, and recorded failures.

## .testicli/ directory structure

Created in the target project after `init`:

```
.testicli/
├── config.yaml              # Detected language, framework, source/test dirs
├── rules.yaml               # Extracted test writing conventions
├── plans/
│   └── plan_<date>_<type>.yaml   # Generated test plans
└── failures/
    └── fail_<timestamp>_<name>.yaml  # Recorded test failures
```

You should commit `config.yaml` and `rules.yaml` to version control. Plans and failures are ephemeral.

## Supported languages

| Language | Framework | Detection |
|---|---|---|
| Python | pytest | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt` |
| JavaScript/TypeScript | jest, vitest | `package.json` |
| Go | go test | `go.mod` |

## Adding a new language

1. Create `src/testicli/languages/your_lang.py` implementing the `LanguageSupport` protocol
2. Register it in `src/testicli/cli.py`:

```python
from testicli.languages.your_lang import YourLangSupport
register_language(YourLangSupport())
```

Required methods: `detect()`, `find_source_files()`, `find_test_files()`, `test_command()`, `test_file_path()`, `parse_test_output()`.

## Adding a new test type

1. Create `src/testicli/test_types/your_type.py` implementing the `TestTypeStrategy` protocol
2. Add the type to the `TestType` enum in `models.py`
3. Register it in `src/testicli/cli.py`:

```python
from testicli.test_types.your_type import YourTypeStrategy
register_test_type(YourTypeStrategy())
```

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Run the CLI locally
uv run testicli --help
```

## License

MIT
