"""Claude Agent SDK engine for Arche."""

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    StreamEvent,
    PermissionResultAllow,
    ToolPermissionContext,
)

from .base import AgentEngine, AgentEvent, EventType


async def auto_approve_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow:
    """Auto-approve all tool usage with 'use your best judgment'."""
    return PermissionResultAllow(behavior="allow")


class ClaudeSDKEngine(AgentEngine):
    """Claude Agent SDK-based engine.

    Uses the official Claude Agent SDK which provides:
    - Real-time streaming with partial messages
    - Built-in tool execution and context management
    - Automatic conversation history
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        permission_mode: str = "plan",
        cwd: Path | None = None,
    ):
        self.model = model
        self.permission_mode = permission_mode
        self.cwd = cwd or Path.cwd()
        self._client: ClaudeSDKClient | None = None
        self._output: str = ""
        self._cancelled = False

    async def run(
        self,
        goal: str,
        system_prompt: str,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute agent using Claude SDK with real-time streaming."""
        self._output = ""
        self._cancelled = False

        yield AgentEvent(type=EventType.STATUS, content="Agent starting")

        try:
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                permission_mode=self.permission_mode,
                model=self.model,
                cwd=self.cwd,
                include_partial_messages=True,
                can_use_tool=auto_approve_tool,  # Auto-approve tool usage
            )

            # Use streaming mode for can_use_tool support
            async def prompt_stream():
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": goal},
                }

            async with ClaudeSDKClient(options=options) as client:
                self._client = client
                await client.connect(prompt_stream())

                async for message in client.receive_response():
                    if self._cancelled:
                        break

                    for event in self._process_message(message):
                        yield event

            yield AgentEvent(type=EventType.COMPLETE, content="Agent completed")

        except asyncio.CancelledError:
            yield AgentEvent(type=EventType.STATUS, content="Agent cancelled")

        except Exception as e:
            yield AgentEvent(type=EventType.ERROR, error=str(e))

        finally:
            self._client = None

    def _process_message(self, message: Any) -> list[AgentEvent]:
        """Convert Claude SDK message to AgentEvents."""
        events = []

        # Handle real-time streaming events
        if isinstance(message, StreamEvent):
            event_data = message.event
            event_type = event_data.get("type", "")

            # content_block_delta contains streaming text
            if event_type == "content_block_delta":
                delta = event_data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        self._output += text
                        events.append(AgentEvent(
                            type=EventType.CONTENT,
                            content=text,
                        ))
                elif delta.get("type") == "thinking_delta":
                    thinking = delta.get("thinking", "")
                    if thinking:
                        events.append(AgentEvent(
                            type=EventType.THINKING,
                            content=thinking,
                        ))

            # content_block_start for tool use
            elif event_type == "content_block_start":
                block = event_data.get("content_block", {})
                if block.get("type") == "tool_use":
                    events.append(AgentEvent(
                        type=EventType.TOOL_CALL,
                        tool_name=block.get("name"),
                        metadata={"tool_id": block.get("id")},
                    ))

        # Handle complete assistant messages
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    # Only add if not already streamed
                    if not self._output.endswith(block.text):
                        self._output += block.text
                        events.append(AgentEvent(
                            type=EventType.CONTENT,
                            content=block.text,
                        ))
                elif isinstance(block, ToolUseBlock):
                    events.append(AgentEvent(
                        type=EventType.TOOL_CALL,
                        tool_name=block.name,
                        tool_args=block.input,
                        metadata={"tool_id": block.id},
                    ))
                elif isinstance(block, ToolResultBlock):
                    events.append(AgentEvent(
                        type=EventType.TOOL_RESULT,
                        tool_result=block.content,
                    ))

        # Handle result message
        elif isinstance(message, ResultMessage):
            events.append(AgentEvent(
                type=EventType.STATUS,
                content=f"Cost: ${message.total_cost_usd:.4f}" if message.total_cost_usd else "Completed",
                metadata={"cost_usd": message.total_cost_usd, "turns": message.num_turns},
            ))

        return events

    async def cancel(self) -> None:
        """Cancel running agent."""
        self._cancelled = True
        if self._client:
            await self._client.interrupt()

    def get_output(self) -> str:
        """Get accumulated text output."""
        return self._output
