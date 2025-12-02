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
    PermissionResultAllow,
    ToolPermissionContext,
)
from claude_agent_sdk.types import (
    StreamEvent,
    HookJSONOutput,
    HookMatcher,
    HookInput,
    HookContext,
)

from .base import AgentEngine, AgentEvent, EventType


# Module-level hook function for auto-approval
async def _auto_approve_hook(
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext,
) -> HookJSONOutput:
    """PreToolUse hook that auto-approves all tools."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


class ClaudeSDKEngine(AgentEngine):
    """Claude Agent SDK-based engine.

    Uses the official Claude Agent SDK which provides:
    - Real-time streaming with partial messages
    - Built-in tool execution and context management
    - Automatic conversation history
    """

    def __init__(
        self,
        model: str | None = None,
        permission_mode: str | None = None,
        auto_approve: bool = False,
        cwd: Path | None = None,
    ):
        self.model = model
        self.permission_mode = permission_mode
        self.auto_approve = auto_approve
        self.cwd = cwd or Path.cwd()
        self._client: ClaudeSDKClient | None = None
        self._output: str = ""
        self._cancelled = False
        # Track current tool blocks for input accumulation
        self._current_tools: dict[int, dict] = {}  # index -> {name, id, input_json}
        self._emitted_tools: set[str] = set()  # tool_ids already emitted

    async def _auto_approve_callback(
        self,
        tool_name: str,
        input_data: dict,
        context: ToolPermissionContext,
    ) -> PermissionResultAllow:
        """Auto-approve all tool permission requests."""
        return PermissionResultAllow()

    async def run(
        self,
        goal: str,
        system_prompt: str,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute agent using Claude SDK with real-time streaming."""
        self._output = ""
        self._cancelled = False
        self._current_tools = {}
        self._emitted_tools = set()

        yield AgentEvent(type=EventType.STATUS, content="Agent starting")

        try:
            opts = {
                "system_prompt": system_prompt,
                "cwd": self.cwd,
                "include_partial_messages": True,
            }
            if self.model:
                opts["model"] = self.model
            if self.permission_mode:
                opts["permission_mode"] = self.permission_mode
            if self.auto_approve:
                # Use both can_use_tool callback and PreToolUse hook for complete auto-approval
                opts["can_use_tool"] = self._auto_approve_callback
                opts["hooks"] = {
                    "PreToolUse": [
                        HookMatcher(matcher=None, hooks=[_auto_approve_hook])
                    ]
                }
            options = ClaudeAgentOptions(**opts)

            # Use streaming mode for can_use_tool support
            async def prompt_stream():
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": goal},
                }

            client = ClaudeSDKClient(options=options)
            self._client = client
            try:
                await client.connect(prompt_stream())

                async for message in client.receive_response():
                    if self._cancelled:
                        break

                    for event in self._process_message(message):
                        yield event

                yield AgentEvent(type=EventType.COMPLETE, content="Agent completed")
            finally:
                await client.disconnect()

        except asyncio.CancelledError:
            yield AgentEvent(type=EventType.STATUS, content="Agent cancelled")

        except Exception as e:
            yield AgentEvent(type=EventType.ERROR, error=str(e))

        finally:
            self._client = None

    def _process_message(self, message: Any) -> list[AgentEvent]:
        """Convert Claude SDK message to AgentEvents."""
        import json as json_module
        events = []

        # Handle real-time streaming events
        if isinstance(message, StreamEvent):
            event_data = message.event
            event_type = event_data.get("type", "")
            index = event_data.get("index", 0)

            # content_block_delta contains streaming text or tool input
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
                elif delta.get("type") == "input_json_delta":
                    # Accumulate tool input JSON
                    if index in self._current_tools:
                        self._current_tools[index]["input_json"] += delta.get("partial_json", "")

            # content_block_start for tool use - track it
            elif event_type == "content_block_start":
                block = event_data.get("content_block", {})
                if block.get("type") == "tool_use":
                    self._current_tools[index] = {
                        "name": block.get("name"),
                        "id": block.get("id"),
                        "input_json": "",
                    }

            # content_block_stop - emit complete tool call event
            elif event_type == "content_block_stop":
                if index in self._current_tools:
                    tool = self._current_tools.pop(index)
                    tool_args = {}
                    if tool["input_json"]:
                        try:
                            tool_args = json_module.loads(tool["input_json"])
                        except json_module.JSONDecodeError:
                            pass
                    self._emitted_tools.add(tool["id"])  # Track emitted
                    events.append(AgentEvent(
                        type=EventType.TOOL_CALL,
                        tool_name=tool["name"],
                        tool_args=tool_args,
                        metadata={"tool_id": tool["id"], "complete": True},
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
                    if block.id not in self._emitted_tools:  # Skip if already emitted from streaming
                        self._emitted_tools.add(block.id)
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
