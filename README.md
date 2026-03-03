# testicli

AI-powered test generator built on Claude. Scans your project, learns conventions from existing tests, generates unit/integration/e2e/fuzzing/security tests, runs them, and auto-fixes failures. Supports Python, JavaScript/TypeScript, and Go, including monorepos.

## Features

- **Interactive TUI** — run `testicli` with no arguments for a menu-driven experience with arrow-key navigation
- **Auto-detection** — detects languages, frameworks, source/test directories, and monorepo subprojects
- **Learns from your code** — analyzes existing tests, extracts naming conventions, assertion styles, mocking patterns as reusable rules
- **5 test types** — unit, integration, e2e, fuzzing (property-based), security (OWASP Top 10)
- **Self-healing** — runs generated tests, auto-fixes failures via Claude, retries
- **Quality gates** — static analysis + optional LLM review, auto-fix for weak tests
- **Failure analysis** — analyzes recurring failures, auto-updates test-writing rules
- **Monorepo support** — per-language configs, per-language rules, separate plans per type/language combo

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and authenticated (`claude login`)

## Installation

```bash
git clone <repo-url>
cd testicli
uv sync
```

## Configuration

Optional environment variables:

| Variable | Default | Description |
|---|---|---|
| `TEST_AGENT_MODEL` | `claude-sonnet-4-6` | Claude model for generation |
| `TEST_AGENT_MAX_FIX_ATTEMPTS` | `2` | Max attempts to fix a failing test |

## Quick start

```bash
# Interactive mode — the easiest way to use testicli
uv run testicli

# Or use subcommands directly
uv run testicli init .
uv run testicli plan -t unit,integration
uv run testicli write
uv run testicli review --fix
uv run testicli status
```

## Usage

### Interactive mode

Run `testicli` with no arguments to launch the interactive TUI:

```
$ uv run testicli

testicli -- AI-powered test generator

? What would you like to do?
> Plan tests
  Write tests
  Review tests
  Show status
  Analyze failures
  Initialize project (re-scan)
  Exit
```

The TUI guides you through every step: picking test types, selecting plans to update, choosing languages in monorepos, and configuring review options — all with arrow keys.

### CLI subcommands

#### `init` — Scan and initialize

```bash
uv run testicli init /path/to/project
```

Detects languages, frameworks, source/test directories, and existing test conventions. Creates `.testicli/` with `config.yaml` and `rules.yaml`.

#### `plan` — Create test plans

```bash
uv run testicli plan -t unit                          # single type
uv run testicli plan -t integration,e2e,security      # multiple types
```

Available types: `unit`, `integration`, `e2e`, `fuzzing`, `security`

Sends source code and extracted rules to Claude, which generates a list of planned tests per type/language combo. Running `plan` again for the same type updates the existing plan (merges new tests).

#### `write` — Generate test code

```bash
uv run testicli write                        # write from latest plan
uv run testicli write --plan integration     # write from specific plan
```

For each pending test: generates code via Claude agent, writes to disk, runs the test. If it fails — sends the error back to Claude for a fix and retries. Persistent failures are recorded for later analysis.

#### `review` — Quality validation

```bash
uv run testicli review                       # static analysis only
uv run testicli review --llm-review          # + LLM-based deep review
uv run testicli review --fix                 # auto-fix weak tests
uv run testicli review --plan unit           # review specific plan
```

Static checks detect empty bodies, missing assertions, trivial assertions (`assert True`), and swallowed errors. LLM review adds semantic analysis. `--fix` attempts auto-repair (reverts if the fix breaks the test).

#### `analyze` — Learn from failures

```bash
uv run testicli analyze                      # view suggestions
uv run testicli analyze --update-rules       # auto-update rules
```

Analyzes recorded failures, identifies patterns, and suggests (or applies) improvements to test-writing rules.

#### `status` — Overview

```bash
uv run testicli status
```

Shows project config, rule count, plans with pass/fail/weak/pending counts, and recorded failures.

## `.testicli/` directory

Created in the target project after `init`:

```
.testicli/
├── config.yaml                          # Language, framework, source/test dirs
├── rules.yaml                           # Extracted test conventions
├── plans/
│   ├── plan_unit_python.yaml            # One file per type/language combo
│   ├── plan_integration_python.yaml
│   └── plan_e2e_javascript.yaml
└── failures/
    └── fail_<timestamp>_<name>.yaml     # Recorded test failures
```

Commit `config.yaml` and `rules.yaml` to version control. Plans and failures are ephemeral.

## Supported languages

| Language | Frameworks | Detected via |
|---|---|---|
| Python | pytest, unittest | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt` |
| JavaScript/TypeScript | Jest, Vitest | `package.json` |
| Go | go test | `go.mod` |

## Extending

### Add a language

1. Create `src/testicli/languages/your_lang.py` implementing the `LanguageSupport` protocol
2. Register in `src/testicli/cli.py`:

```python
from testicli.languages.your_lang import YourLangSupport
register_language(YourLangSupport())
```

### Add a test type

1. Create `src/testicli/test_types/your_type.py` implementing `TestTypeStrategy`
2. Add the type to the `TestType` enum in `models.py`
3. Register in `src/testicli/cli.py`:

```python
from testicli.test_types.your_type import YourTypeStrategy
register_test_type(YourTypeStrategy())
```

## Development

```bash
uv sync
uv run pytest tests/ -v
uv run testicli --help
```

## License

MIT
