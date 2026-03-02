"""Anthropic SDK wrapper with retries and structured output."""


import json
import time
from typing import Any

import anthropic
from rich.console import Console

from testicli.config import Settings

console = Console()

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.model

    def generate_text(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Simple text generation."""
        temp = temperature if temperature is not None else self.settings.analysis_temperature
        response = self._call_api(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp,
            max_tokens=max_tokens,
        )
        return self._extract_text(response)

    def generate_structured(
        self,
        system: str,
        prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Structured output via forced tool_use."""
        temp = temperature if temperature is not None else self.settings.analysis_temperature
        tools = [
            {
                "name": tool_name,
                "description": f"Output structured {tool_name} data",
                "input_schema": tool_schema,
            }
        ]
        response = self._call_api(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
        )
        return self._extract_tool_input(response, tool_name)

    def generate_code(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 8192,
    ) -> str:
        """Code generation with temperature=0."""
        response = self._call_api(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.settings.code_temperature,
            max_tokens=max_tokens,
        )
        return self._extract_text(response)

    def _call_api(self, **kwargs: Any) -> anthropic.types.Message:
        """Call the API with exponential backoff retry."""
        kwargs["model"] = self.model
        for attempt in range(MAX_RETRIES):
            try:
                return self.client.messages.create(**kwargs)
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                console.print(f"[yellow]API retry in {delay}s: {e}[/yellow]")
                time.sleep(delay)
        raise RuntimeError("Unreachable")

    @staticmethod
    def _extract_text(response: anthropic.types.Message) -> str:
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _extract_tool_input(response: anthropic.types.Message, tool_name: str) -> dict[str, Any]:
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input  # type: ignore[return-value]
        raise ValueError(f"No tool_use block found for {tool_name}")
