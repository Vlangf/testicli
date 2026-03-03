"""Unit test strategy."""


from testicli.models import TestType


class UnitStrategy:
    test_type = TestType.UNIT

    def build_planning_context(self, source_files_content: str) -> str:
        return (
            "Focus on testing individual functions, methods, and classes in isolation. "
            "Look for:\n"
            "- Pure functions with clear inputs and outputs\n"
            "- Class methods that can be tested independently\n"
            "- Edge cases and boundary conditions\n"
            "- Error handling paths\n"
        )

    def planning_prompt_additions(self) -> str:
        return (
            "Generate unit tests that verify individual units of code in isolation. "
            "Each test should focus on a single function or method. "
            "Mock all external dependencies to isolate the unit under test."
        )

    def writing_prompt_additions(self) -> str:
        return (
            "Write a unit test. Guidelines:\n"
            "- Test a single function or method in isolation\n"
            "- Mock all external dependencies\n"
            "- Cover happy path, edge cases, and error conditions\n"
            "- Use descriptive test names that explain the expected behavior\n"
        )
