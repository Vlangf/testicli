"""All prompt templates for Claude API calls."""


# --- Analyzer prompts ---

ANALYZE_TESTS_SYSTEM = """\
You are an expert test engineer. Analyze the existing test files and extract \
conventions, patterns, and rules used in this project's test suite.
Focus on:
- Naming conventions (files, classes, functions)
- Setup/teardown patterns (fixtures, setUp/tearDown, beforeEach)
- Assertion styles
- Mocking patterns
- File organization
- Common helpers or utilities used
"""

ANALYZE_TESTS_PROMPT = """\
Project language: {language}
Test framework: {framework}

Here are the existing test files:

{test_files_content}

Extract the test writing rules and conventions from these files. \
For each rule, provide:
- category: the aspect of testing it covers (naming, setup, assertions, mocking, structure, etc.)
- pattern: a concise description of the pattern
- example: a brief code example if applicable
- confidence: how confident you are this is an intentional convention (0.0 to 1.0)
"""

ANALYZE_TESTS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "pattern": {"type": "string"},
                    "example": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["category", "pattern", "confidence"],
            },
        }
    },
    "required": ["rules"],
}

# --- Planner prompts ---

PLAN_TESTS_SYSTEM = """\
You are an expert test engineer. Your task is to create a detailed test plan \
for the given source code. Consider the existing test rules and conventions.
Generate tests that are practical, focused, and cover important behavior.
"""

PLAN_TESTS_PROMPT = """\
Project language: {language}
Test framework: {framework}
Test type to generate: {test_type}
Test output directory: {test_dir}

{type_specific_context}

Existing test rules/conventions:
{rules}

Source files to test:
{source_files_content}
{already_covered_section}
{existing_tests_section}
Create a test plan. For each planned test, provide:
- id: a unique identifier (e.g., "test_001")
- name: descriptive test name
- description: what the test verifies
- target_file: the source file being tested
- output_file: where to write the test (must be inside the test output directory above)
"""

PLAN_TESTS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "target_file": {"type": "string"},
                    "output_file": {"type": "string"},
                },
                "required": ["id", "name", "description", "target_file", "output_file"],
            },
        }
    },
    "required": ["tests"],
}

# --- Writer prompts (agentic mode) ---

WRITE_TEST_SYSTEM_AGENTIC = """\
You are an expert test engineer.
Write a production-quality test file using the write_file tool.

IMPORTANT:
- You MUST call write_file with the complete test code
- Include all necessary imports
- Follow the project's existing test conventions exactly
- Make tests deterministic and independent
- Do NOT output the code as text — use the write_file tool
"""

WRITE_TEST_PROMPT = """\
Project language: {language}
Test framework: {framework}

Test conventions to follow:
{rules}

{type_specific_additions}

Source file under test ({target_file}):
```
{source_content}
```

Write a test for:
- Name: {test_name}
- Description: {test_description}

Write the test code to file: {output_file}
Use the write_file tool to create the file.
"""

FIX_TEST_SYSTEM_AGENTIC = """\
You are an expert test engineer. Fix the failing test code based on the error output.

IMPORTANT:
- You MUST call write_file with the complete fixed test code
- Preserve all imports and test structure
- Fix only what's broken, don't change test intent
- Do NOT output the code as text — use the write_file tool
"""

FIX_TEST_PROMPT = """\
The following test failed. Fix it.

Test code:
```
{test_code}
```

Error output:
```
{error_output}
```

Source file under test ({target_file}):
```
{source_content}
```

Write the fixed test code to file: {output_file}
Use the write_file tool to create the file.
"""

# --- Failure analyzer prompts ---

ANALYZE_FAILURE_SYSTEM = """\
You are an expert test engineer. Analyze test failures to identify patterns \
and suggest improvements to test writing rules.
"""

ANALYZE_FAILURE_PROMPT = """\
Analyze these test failures and suggest rule improvements:

{failures_content}

Current rules:
{rules}

For each suggestion:
- What rule to add or modify
- Why (based on failure patterns)
- Example of the improved approach
"""

ANALYZE_FAILURE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "modify", "remove"]},
                    "category": {"type": "string"},
                    "pattern": {"type": "string"},
                    "example": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["action", "category", "pattern", "reason"],
            },
        }
    },
    "required": ["suggestions"],
}

# --- Quality review prompts ---

QUALITY_REVIEW_SYSTEM = """\
You are an expert test quality reviewer. Analyze the test code for quality issues \
that static analysis cannot catch. Focus on:
- Whether the test actually verifies meaningful behavior of the target code
- Whether assertions are testing the right things (not just "no exception thrown")
- Whether edge cases and error paths are covered
- Whether mocking is done correctly (not mocking the thing under test)
- Whether the test would catch real bugs in the target code
"""

QUALITY_REVIEW_PROMPT = """\
Review this test for quality issues.

Test file ({test_name}):
```
{test_code}
```

Source file under test ({target_file}):
```
{source_code}
```

Find quality issues. For each issue provide:
- code: a short identifier (e.g., "weak_assertion", "missing_edge_case", "mocking_target")
- severity: "error" for serious issues that make the test meaningless, "warning" for improvements
- message: human-readable description
- line: line number in the test file (if applicable, otherwise null)
"""

QUALITY_REVIEW_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "severity": {"type": "string", "enum": ["error", "warning"]},
                    "message": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                },
                "required": ["code", "severity", "message"],
            },
        }
    },
    "required": ["issues"],
}

FIX_QUALITY_SYSTEM = """\
You are an expert test engineer. Fix the quality issues in the test code. \
The test currently passes but has quality problems that make it weak or meaningless.

IMPORTANT:
- Output ONLY the complete fixed test code, no markdown fences, no explanations
- The fixed test must still pass when run
- Preserve the overall test structure but strengthen assertions and coverage
- Add meaningful assertions that verify actual behavior
"""

FIX_QUALITY_PROMPT = """\
Fix the following quality issues in this test.

Test code:
```
{test_code}
```

Source file under test ({target_file}):
```
{source_content}
```

Quality issues found:
{issues_text}

Output ONLY the complete fixed test code.
"""
