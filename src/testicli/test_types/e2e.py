"""E2E test strategy."""


from testicli.models import TestType


class E2EStrategy:
    test_type = TestType.E2E

    def build_planning_context(self, source_files_content: str) -> str:
        return (
            "Focus on testing complete user workflows end-to-end. Look for:\n"
            "- Entry points (CLI commands, API endpoints, main functions)\n"
            "- Complete user scenarios from input to output\n"
            "- External system interactions\n"
        )

    def planning_prompt_additions(self) -> str:
        return (
            "Generate end-to-end tests that simulate real user scenarios. "
            "Each test should cover a complete workflow from start to finish. "
            "Test the system as a black box where possible."
        )

    def writing_prompt_additions(self) -> str:
        return (
            "Write an end-to-end test. Guidelines:\n"
            "- Test complete user workflows\n"
            "- Use the system's public interface (CLI, API, etc.)\n"
            "- Verify final output/state, not intermediate steps\n"
            "- Set up and tear down test environment properly\n"
        )
