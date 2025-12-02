"""DeepAgents engine for Arche.

Uses LangGraph-based DeepAgents framework.
"""

import asyncio
from typing import Any, AsyncIterator

from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from .base import AgentEngine, AgentEvent, EventType


class DeepAgentsEngine(AgentEngine):
    """DeepAgents-based engine using LangGraph.

    Uses the DeepAgents framework which provides:
    - Built-in middleware (TodoList, Summarization, Filesystem)
    - Sub-agent delegation via `task` tool
    - Compatible with any LangChain model
    """

    def __init__(
        self,
        model: str = "anthropic:claude-sonnet-4-20250514",
        temperature: float = 0.7,
    ):
        self.model = model
        self.temperature = temperature
        self._output: str = ""
        self._cancelled = False

    def _create_model(self):
        """Create LangChain model instance."""
        import os

        if ":" in self.model:
            provider, model_name = self.model.split(":", 1)
        else:
            provider = "anthropic" if "claude" in self.model else "openai"
            model_name = self.model

        if provider == "anthropic":
            return ChatAnthropic(model=model_name, temperature=self.temperature)

        if provider == "openrouter":
            return ChatOpenAI(
                model=model_name,
                temperature=self.temperature,
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            )

        if provider == "openai":
            return ChatOpenAI(model=model_name, temperature=self.temperature)

        if provider == "deepseek":
            return ChatOpenAI(
                model=model_name,
                temperature=self.temperature,
                base_url="https://api.deepseek.com/v1",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
            )

        raise ValueError(f"Unknown provider: {provider}")

    async def run(
        self,
        goal: str,
        system_prompt: str,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute agent using DeepAgents."""
        self._output = ""
        self._cancelled = False

        yield AgentEvent(type=EventType.STATUS, content="Agent starting")

        try:
            model = self._create_model()
            agent = create_deep_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
            )

            async for chunk in agent.astream({"messages": [{"role": "user", "content": goal}]}):
                if self._cancelled:
                    break

                for event in self._parse_chunk(chunk):
                    yield event

            yield AgentEvent(type=EventType.COMPLETE, content="Agent completed")

        except asyncio.CancelledError:
            yield AgentEvent(type=EventType.STATUS, content="Agent cancelled")

        except Exception as e:
            yield AgentEvent(type=EventType.ERROR, error=str(e))

    def _parse_chunk(self, chunk: Any) -> list[AgentEvent]:
        """Parse LangGraph stream chunk into AgentEvents."""
        events = []

        if not isinstance(chunk, dict):
            return events

        messages = chunk.get("messages")
        if messages and isinstance(messages, list):
            for msg in messages:
                if msg is None:
                    continue

                content = getattr(msg, "content", None)
                if content:
                    self._output += str(content)
                    events.append(AgentEvent(
                        type=EventType.CONTENT,
                        content=str(content),
                    ))

                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls and isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            events.append(AgentEvent(
                                type=EventType.TOOL_CALL,
                                tool_name=tc.get("name"),
                                tool_args=tc.get("args"),
                            ))

        return events

    async def cancel(self) -> None:
        """Cancel running agent."""
        self._cancelled = True

    def get_output(self) -> str:
        """Get accumulated text output."""
        return self._output
