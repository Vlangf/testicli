"""Base protocol for test type strategies."""


from typing import Protocol, runtime_checkable

from testicli.models import TestType


@runtime_checkable
class TestTypeStrategy(Protocol):
    test_type: TestType

    def build_planning_context(self, source_files_content: str) -> str:
        """Build additional context for the planning prompt."""
        ...

    def planning_prompt_additions(self) -> str:
        """Additional instructions for the planning prompt."""
        ...

    def writing_prompt_additions(self) -> str:
        """Additional instructions for the test writing prompt."""
        ...


# Registry
_registry: dict[TestType, TestTypeStrategy] = {}


def register_test_type(strategy: TestTypeStrategy) -> None:
    _registry[strategy.test_type] = strategy


def get_test_type_strategy(test_type: TestType) -> TestTypeStrategy | None:
    return _registry.get(test_type)
