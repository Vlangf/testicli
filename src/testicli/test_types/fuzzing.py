"""Fuzz / property-based test strategy."""


from testicli.models import TestType


class FuzzingStrategy:
    test_type = TestType.FUZZING

    def build_planning_context(self, source_files_content: str) -> str:
        return (
            "Focus on finding edge cases and unexpected inputs. Look for:\n"
            "- Functions that parse or validate input\n"
            "- Data transformation functions\n"
            "- Serialization/deserialization code\n"
            "- Boundary conditions in algorithms\n"
        )

    def planning_prompt_additions(self) -> str:
        return (
            "Generate property-based / fuzz tests. "
            "Each test should use hypothesis (Python), fast-check (JS), or similar libraries "
            "to generate random inputs and verify invariants. "
            "Focus on functions that accept complex input."
        )

    def writing_prompt_additions(self) -> str:
        return (
            "Write a property-based / fuzz test. Guidelines:\n"
            "- Use hypothesis library for Python (@given decorator)\n"
            "- Define clear invariants that should hold for all inputs\n"
            "- Test edge cases: empty strings, large numbers, special characters\n"
            "- Ensure the function doesn't crash on any input\n"
        )
