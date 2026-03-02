"""Claude Agent SDK wrapper with structured output support."""


import asyncio
import json
import re
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    AssistantMessage,
    SdkMcpTool,
    TextBlock,
    create_sdk_mcp_server,
    query,
)
from rich.console import Console

from testicli.config import Settings

console = Console()


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_text(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Simple text generation."""
        return asyncio.run(self._query_text(system, prompt))

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
        """Structured output via JSON in prompt."""
        return asyncio.run(self._query_structured(system, prompt, tool_schema))

    def generate_code(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 8192,
    ) -> str:
        """Code generation."""
        return asyncio.run(self._query_text(system, prompt))

    def generate_with_tools(
        self,
        system: str,
        prompt: str,
        tools: list[SdkMcpTool],
        *,
        max_turns: int = 5,
    ) -> str:
        """Run Claude in agent mode with MCP tools. Returns collected text."""
        return asyncio.run(self._query_agentic(system, prompt, tools, max_turns))

    async def _query_agentic(
        self,
        system: str,
        prompt: str,
        tools: list[SdkMcpTool],
        max_turns: int,
    ) -> str:
        """Run Claude in agent mode with in-process MCP tools."""
        mcp_server = create_sdk_mcp_server(name="testicli_tools", tools=tools)
        options = ClaudeAgentOptions(
            model=self.settings.model,
            system_prompt=system,
            mcp_servers={"testicli_tools": mcp_server},
            allowed_tools=[t.name for t in tools],
            max_turns=max_turns,
        )
        parts: list[str] = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        return "\n".join(parts)

    async def _query_text(self, system: str, prompt: str) -> str:
        """Send a query and collect text from the response."""
        options = ClaudeAgentOptions(
            model=self.settings.model,
            system_prompt=system,
            max_turns=1,
        )
        parts: list[str] = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        return "\n".join(parts)

    async def _query_structured(
        self, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a query expecting JSON output, parse the response."""
        schema_str = json.dumps(schema, indent=2)
        structured_prompt = (
            f"{prompt}\n\n"
            f"You MUST respond with ONLY valid JSON matching this schema:\n"
            f"```json\n{schema_str}\n```\n"
            f"Do not include any text outside the JSON object."
        )
        raw = await self._query_text(system, structured_prompt)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Parse JSON from response, handling markdown code blocks."""
        # Try direct parse first
        stripped = text.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_start = stripped.find("{")
        brace_end = stripped.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                return json.loads(stripped[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse JSON from response:\n{text[:500]}")
