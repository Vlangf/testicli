"""Integration test strategy."""


from testicli.models import TestType


class IntegrationStrategy:
    test_type = TestType.INTEGRATION

    def build_planning_context(self, source_files_content: str) -> str:
        return (
            "Focus on testing interactions between modules, classes, and functions. "
            "Look for:\n"
            "- Functions/methods that call other modules\n"
            "- Data flow between components\n"
            "- Database or file system interactions\n"
            "- API endpoint handlers\n"
        )

    def planning_prompt_additions(self) -> str:
        return (
            "Generate integration tests that verify correct interaction between components. "
            "Each test should exercise a real code path through multiple layers. "
            "Use real objects where possible, mock only external services."
        )

    def writing_prompt_additions(self) -> str:
        return (
            "Write an integration test. Guidelines:\n"
            "- Test real interactions between components\n"
            "- Only mock external services (network, databases) if necessary\n"
            "- Use realistic test data\n"
            "- Verify end-to-end behavior, not just individual units\n"
        )
