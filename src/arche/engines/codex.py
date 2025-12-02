"""Codex SDK engine for Arche (placeholder).

OpenAI Codex SDK support - coming when Python SDK is available.
Currently only TypeScript SDK exists.
"""

from typing import Any, AsyncIterator

from .base import AgentEngine, AgentEvent, EventType


class CodexEngine(AgentEngine):
    """Codex SDK-based engine (placeholder).

    Will be implemented when OpenAI releases Python SDK for Codex.
    """

    def __init__(self, **kwargs):
        raise NotImplementedError(
            "Codex SDK Python is not yet available. "
            "Only TypeScript SDK exists currently."
        )

    async def run(
        self,
        goal: str,
        system_prompt: str,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Not implemented."""
        raise NotImplementedError("Codex SDK not available")
        yield  # type: ignore

    async def cancel(self) -> None:
        """Not implemented."""
        pass

    def get_output(self) -> str:
        """Not implemented."""
        return ""
