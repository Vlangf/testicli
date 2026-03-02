"""Analyze failures and suggest rule improvements."""


from rich.console import Console

from testicli.llm.client import LLMClient
from testicli.llm.prompts import (
    ANALYZE_FAILURE_PROMPT,
    ANALYZE_FAILURE_SYSTEM,
    ANALYZE_FAILURE_TOOL_SCHEMA,
)
from testicli.models import TestFailure, TestRule

console = Console()


def analyze_failures(
    llm: LLMClient,
    current_rules: list[TestRule],
    failures: list[TestFailure],
) -> list[TestRule]:
    """Analyze failures and return updated rules."""
    failures_content = []
    for f in failures:
        failures_content.append(
            f"--- {f.test_name} (attempt {f.attempt}) ---\n"
            f"Error type: {f.error_type}\n"
            f"Error output:\n{f.error_output[:2000]}\n"
            f"Test code:\n{f.test_code[:2000]}\n"
        )

    rules_text = "\n".join(f"- [{r.category}] {r.pattern}" for r in current_rules) or "No rules."

    prompt = ANALYZE_FAILURE_PROMPT.format(
        failures_content="\n\n".join(failures_content),
        rules=rules_text,
    )

    result = llm.generate_structured(
        system=ANALYZE_FAILURE_SYSTEM,
        prompt=prompt,
        tool_name="suggest_rules",
        tool_schema=ANALYZE_FAILURE_TOOL_SCHEMA,
        temperature=0.3,
    )

    suggestions = result.get("suggestions", [])

    # Apply suggestions to current rules
    updated_rules = list(current_rules)

    for s in suggestions:
        action = s.get("action", "add")
        category = s.get("category", "")
        pattern = s.get("pattern", "")
        reason = s.get("reason", "")

        console.print(f"  [{action}] {category}: {pattern}")
        console.print(f"    Reason: {reason}")

        if action == "add":
            updated_rules.append(
                TestRule(
                    category=category,
                    pattern=pattern,
                    example=s.get("example", ""),
                    confidence=0.7,
                )
            )
        elif action == "modify":
            for r in updated_rules:
                if r.category == category:
                    r.pattern = pattern
                    if s.get("example"):
                        r.example = s["example"]
                    break
        elif action == "remove":
            updated_rules = [r for r in updated_rules if r.category != category]

    return updated_rules
