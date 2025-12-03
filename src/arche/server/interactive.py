"""Interactive mode session manager for Claude Code-like experience.

Multi-session management with real-time WebSocket communication,
human-in-the-loop permission handling, and streaming responses.

Supports both Claude SDK and DeepAgents engines with full middleware support.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
)
from claude_agent_sdk.types import StreamEvent

# Import domain models from core - eliminates duplicate dataclass definitions
from arche.core import (
    # Enums
    EngineType,
    AgentCapability,
    SessionState,
    MessageRole,
    # Domain models
    TodoItem,
    SubAgentTask,
    FileOperation,
    SkillInfo,
    ContentBlock,
    Message,
    PermissionRequest,
    # Events
    event_bus,
    # Strategy patterns
    PermissionStrategyFactory,
)
from arche.core.domain import DEFAULT_CAPABILITIES, THINKING_BUDGETS, PLAN_MODE_TOOLS


@dataclass
class Session:
    """An interactive Claude session with DeepAgents support."""
    id: str
    name: str
    state: SessionState = SessionState.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Configuration
    model: str = "claude-sonnet-4-20250514"
    cwd: str = ""
    permission_mode: str = "default"  # default, acceptEdits, plan, bypassPermissions
    resume_session_id: str | None = None  # Session ID to resume from Claude CLI

    # Engine selection (DeepAgents support)
    engine: str = "claude_sdk"  # claude_sdk | deepagents
    enabled_capabilities: list[str] = field(default_factory=lambda: DEFAULT_CAPABILITIES.copy())

    # Conversation
    messages: list[Message] = field(default_factory=list)

    # Execution state
    current_turn: int = 0
    total_cost_usd: float = 0.0
    pending_permission: PermissionRequest | None = None

    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0

    # DeepAgents state
    todos: list[TodoItem] = field(default_factory=list)
    subagent_tasks: list[SubAgentTask] = field(default_factory=list)
    file_operations: list[FileOperation] = field(default_factory=list)
    loaded_skills: list[str] = field(default_factory=list)

    # Extended features
    thinking_mode: str = "normal"  # normal, think, think_hard, ultrathink
    plan_mode_active: bool = False
    proposed_plan: dict | None = None
    background_tasks: list[str] = field(default_factory=list)  # Task IDs
    checkpoints: list[str] = field(default_factory=list)  # Checkpoint IDs
    mcp_servers: list[str] = field(default_factory=list)  # Connected MCP server names
    budget_usd: float | None = None  # Max budget for session
    system_prompt: str | None = None  # Custom system prompt

    # Approval system
    pending_approval: dict | None = None  # {mode, result, created_at}

    # Internal
    _client: ClaudeSDKClient | None = field(default=None, repr=False)
    _deepagent: Any = field(default=None, repr=False)  # DeepAgents compiled graph
    _task: asyncio.Task | None = field(default=None, repr=False)
    _message_queue: asyncio.Queue | None = field(default=None, repr=False)
    _permission_response: asyncio.Future | None = field(default=None, repr=False)

    def to_dict(self, include_messages: bool = False) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "model": self.model,
            "cwd": self.cwd,
            "permission_mode": self.permission_mode,
            "resume_session_id": self.resume_session_id,
            "current_turn": self.current_turn,
            "total_cost_usd": self.total_cost_usd,
            "pending_permission": self.pending_permission.to_dict() if self.pending_permission else None,
            "message_count": len(self.messages),
            "is_resumable": False,  # Active sessions are not resumable (they're already active)
            # Engine selection
            "engine": self.engine,
            "enabled_capabilities": self.enabled_capabilities,
            # Token tracking
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            # DeepAgents state
            "todos": [t.to_dict() for t in self.todos],
            "subagent_tasks": [t.to_dict() for t in self.subagent_tasks],
            "file_operations": [f.to_dict() for f in self.file_operations[-20:]],  # Last 20
            "loaded_skills": self.loaded_skills,
            # Extended features
            "thinking_mode": self.thinking_mode,
            "plan_mode_active": self.plan_mode_active,
            "proposed_plan": self.proposed_plan,
            "background_tasks": self.background_tasks,
            "checkpoints": self.checkpoints,
            "mcp_servers": self.mcp_servers,
            "budget_usd": self.budget_usd,
            "system_prompt": self.system_prompt,
        }
        if include_messages:
            result["messages"] = [m.to_dict() for m in self.messages]
        return result


# Legacy type alias for backward compatibility
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class SessionManager:
    """Manages multiple interactive Claude sessions.

    Uses centralized EventBus for all broadcasts.
    """

    def __init__(self, default_cwd: Path | None = None):
        self.sessions: dict[str, Session] = {}
        self.default_cwd = default_cwd or Path.cwd()
        self._lock = asyncio.Lock()

    def set_broadcast_callback(self, callback: BroadcastCallback):
        """Set legacy callback - now routes through event_bus.

        This callback is set on event_bus to maintain backward compatibility.
        """
        event_bus.set_legacy_callback(callback)

    async def _broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast message to session's WebSocket clients via EventBus."""
        await event_bus.broadcast(session_id, message)

    async def create_session(
        self,
        name: str | None = None,
        model: str | None = None,
        cwd: str | None = None,
        permission_mode: str = "default",
        resume: str | None = None,
        engine: str = "claude_sdk",
        capabilities: list[str] | None = None,
    ) -> Session:
        """Create a new interactive session or resume an existing one.

        Args:
            name: Session name
            model: Model ID to use
            cwd: Working directory
            permission_mode: Permission mode (default, acceptEdits, plan, bypassPermissions)
            resume: Session ID from Claude CLI to resume
            engine: Engine to use (claude_sdk, deepagents)
            capabilities: DeepAgents capabilities to enable
        """
        session_id = str(uuid.uuid4())[:8]

        # Generate name based on resume status and engine
        if resume:
            session_name = name or f"Resumed: {resume[:8]}"
        elif engine == "deepagents":
            session_name = name or f"DeepAgent {len(self.sessions) + 1}"
        else:
            session_name = name or f"Session {len(self.sessions) + 1}"

        session = Session(
            id=session_id,
            name=session_name,
            model=model or "claude-sonnet-4-20250514",
            cwd=cwd or str(self.default_cwd),
            permission_mode=permission_mode,
            resume_session_id=resume,
            engine=engine,
            enabled_capabilities=capabilities or DEFAULT_CAPABILITIES.copy(),
            _message_queue=asyncio.Queue(),
        )

        async with self._lock:
            self.sessions[session_id] = session

        await self._broadcast_to_session(session_id, {
            "type": "session_created",
            "session": session.to_dict(),
        })

        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        """List all sessions with basic info."""
        return [s.to_dict() for s in self.sessions.values()]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        # Cancel any running task
        if session._task and not session._task.done():
            session._task.cancel()
            try:
                await session._task
            except asyncio.CancelledError:
                pass

        # Disconnect client
        if session._client:
            try:
                await session._client.disconnect()
            except Exception:
                pass

        async with self._lock:
            del self.sessions[session_id]

        await self._broadcast_to_session(session_id, {
            "type": "session_deleted",
            "session_id": session_id,
        })

        return True

    async def send_message(
        self,
        session_id: str,
        content: str,
        system_prompt: str | None = None,
    ) -> bool:
        """Send a user message to start/continue conversation."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if session.state not in (SessionState.IDLE, SessionState.COMPLETED, SessionState.ERROR):
            # Can't send message while processing
            return False

        # Add user message
        user_msg = Message(
            id=str(uuid.uuid4())[:8],
            role=MessageRole.USER,
            content=[ContentBlock(type="text", content=content)],
        )
        session.messages.append(user_msg)
        session.current_turn += 1
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "message",
            "message": user_msg.to_dict(),
        })

        # Start processing in background - select engine
        if session.engine == "deepagents":
            session._task = asyncio.create_task(
                self._process_deepagents_conversation(session, content, system_prompt)
            )
        else:
            session._task = asyncio.create_task(
                self._process_conversation(session, content, system_prompt)
            )

        return True

    async def _process_conversation(
        self,
        session: Session,
        prompt: str,
        system_prompt: str | None = None,
    ):
        """Process conversation with Claude SDK."""
        session.state = SessionState.THINKING
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session.id, {
            "type": "state_change",
            "state": session.state.value,
        })

        try:
            # Build options
            opts: dict[str, Any] = {
                "cwd": session.cwd,
                "include_partial_messages": True,
            }

            if session.model:
                opts["model"] = session.model

            # Use session's system prompt or provided one
            effective_system_prompt = system_prompt or session.system_prompt
            if effective_system_prompt:
                opts["system_prompt"] = effective_system_prompt

            # Thinking mode configuration
            if session.thinking_mode != "normal" and session.thinking_mode in THINKING_BUDGETS:
                budget = THINKING_BUDGETS[session.thinking_mode]
                if budget:
                    opts["thinking"] = {"type": "enabled", "budget_tokens": budget}

            # Budget control
            if session.budget_usd:
                opts["max_budget_usd"] = session.budget_usd

            # Permission strategy - replaces if-else chain with Strategy pattern
            permission_factory = PermissionStrategyFactory(self._create_permission_callback)
            permission_strategy = permission_factory.create(session)
            permission_strategy.configure_options(opts, session)

            # Resume from existing Claude CLI session
            if session.resume_session_id:
                opts["resume"] = session.resume_session_id

            options = ClaudeAgentOptions(**opts)

            # Create prompt stream
            async def prompt_stream():
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": prompt},
                    "session_id": session.id,
                }

            client = ClaudeSDKClient(options=options)
            session._client = client

            await client.connect(prompt_stream())

            # Current assistant message being built
            current_blocks: list[ContentBlock] = []
            current_text = ""
            current_tools: dict[int, dict] = {}
            emitted_tools: set[str] = set()

            async for message in client.receive_response():
                if session.state == SessionState.INTERRUPTED:
                    break

                # Process StreamEvent (real-time updates)
                if isinstance(message, StreamEvent):
                    event_data = message.event
                    event_type = event_data.get("type", "")
                    index = event_data.get("index", 0)

                    if event_type == "content_block_delta":
                        delta = event_data.get("delta", {})
                        delta_type = delta.get("type")

                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                current_text += text
                                await self._broadcast_to_session(session.id, {
                                    "type": "stream",
                                    "stream_type": "text",
                                    "content": text,
                                })

                        elif delta_type == "thinking_delta":
                            thinking = delta.get("thinking", "")
                            if thinking:
                                await self._broadcast_to_session(session.id, {
                                    "type": "stream",
                                    "stream_type": "thinking",
                                    "content": thinking,
                                })

                        elif delta_type == "input_json_delta":
                            if index in current_tools:
                                current_tools[index]["input_json"] += delta.get("partial_json", "")

                    elif event_type == "content_block_start":
                        block = event_data.get("content_block", {})
                        block_type = block.get("type")

                        if block_type == "tool_use":
                            session.state = SessionState.TOOL_EXECUTING
                            current_tools[index] = {
                                "name": block.get("name"),
                                "id": block.get("id"),
                                "input_json": "",
                            }
                            await self._broadcast_to_session(session.id, {
                                "type": "state_change",
                                "state": session.state.value,
                            })

                    elif event_type == "content_block_stop":
                        if index in current_tools:
                            tool = current_tools.pop(index)
                            tool_args = {}
                            if tool["input_json"]:
                                try:
                                    tool_args = json.loads(tool["input_json"])
                                except json.JSONDecodeError:
                                    pass

                            if tool["id"] not in emitted_tools:
                                emitted_tools.add(tool["id"])
                                current_blocks.append(ContentBlock(
                                    type="tool_use",
                                    content=tool_args,
                                    tool_id=tool["id"],
                                    tool_name=tool["name"],
                                ))
                                await self._broadcast_to_session(session.id, {
                                    "type": "tool_use",
                                    "tool_id": tool["id"],
                                    "tool_name": tool["name"],
                                    "tool_input": tool_args,
                                })

                # Process complete AssistantMessage
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            if block.text and block.text not in current_text:
                                current_text += block.text

                        elif isinstance(block, ThinkingBlock):
                            current_blocks.append(ContentBlock(
                                type="thinking",
                                content=block.thinking,
                            ))

                        elif isinstance(block, ToolUseBlock):
                            if block.id not in emitted_tools:
                                emitted_tools.add(block.id)
                                current_blocks.append(ContentBlock(
                                    type="tool_use",
                                    content=block.input,
                                    tool_id=block.id,
                                    tool_name=block.name,
                                ))

                        elif isinstance(block, ToolResultBlock):
                            current_blocks.append(ContentBlock(
                                type="tool_result",
                                content=block.content,
                                tool_id=block.tool_use_id,
                            ))
                            await self._broadcast_to_session(session.id, {
                                "type": "tool_result",
                                "tool_id": block.tool_use_id,
                                "content": block.content if isinstance(block.content, str) else str(block.content),
                                "is_error": block.is_error if hasattr(block, 'is_error') else False,
                            })

                # Process ResultMessage (completion)
                elif isinstance(message, ResultMessage):
                    if message.total_cost_usd:
                        session.total_cost_usd += message.total_cost_usd

                    await self._broadcast_to_session(session.id, {
                        "type": "result",
                        "cost_usd": message.total_cost_usd,
                        "num_turns": message.num_turns,
                        "is_error": message.is_error,
                    })

            # Finalize assistant message
            if current_text:
                current_blocks.insert(0, ContentBlock(type="text", content=current_text))

            if current_blocks:
                assistant_msg = Message(
                    id=str(uuid.uuid4())[:8],
                    role=MessageRole.ASSISTANT,
                    content=current_blocks,
                    metadata={"cost_usd": session.total_cost_usd},
                )
                session.messages.append(assistant_msg)

                await self._broadcast_to_session(session.id, {
                    "type": "message",
                    "message": assistant_msg.to_dict(),
                })

            session.state = SessionState.COMPLETED

        except asyncio.CancelledError:
            session.state = SessionState.INTERRUPTED
            await self._broadcast_to_session(session.id, {
                "type": "interrupted",
            })

        except Exception as e:
            session.state = SessionState.ERROR
            await self._broadcast_to_session(session.id, {
                "type": "error",
                "error": str(e),
            })

        finally:
            session.updated_at = datetime.now()
            session._client = None

            await self._broadcast_to_session(session.id, {
                "type": "state_change",
                "state": session.state.value,
            })

    def _create_permission_callback(self, session: Session):
        """Create permission callback for human-in-the-loop."""
        async def can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: Any,
        ) -> dict:
            # Create permission request
            request_id = str(uuid.uuid4())[:8]
            session.pending_permission = PermissionRequest(
                request_id=request_id,
                tool_name=tool_name,
                tool_input=tool_input,
                suggestions=getattr(context, 'suggestions', None),
            )
            session.state = SessionState.PERMISSION_PENDING
            session.updated_at = datetime.now()

            # Broadcast permission request
            await self._broadcast_to_session(session.id, {
                "type": "permission_request",
                "request": session.pending_permission.to_dict(),
            })

            await self._broadcast_to_session(session.id, {
                "type": "state_change",
                "state": session.state.value,
            })

            # Wait for response
            session._permission_response = asyncio.get_event_loop().create_future()

            try:
                # Timeout after 5 minutes
                result = await asyncio.wait_for(
                    session._permission_response,
                    timeout=300.0
                )
                return result
            except asyncio.TimeoutError:
                return {
                    "behavior": "deny",
                    "message": "Permission request timed out",
                }
            finally:
                session.pending_permission = None
                session._permission_response = None
                if session.state == SessionState.PERMISSION_PENDING:
                    session.state = SessionState.THINKING
                    await self._broadcast_to_session(session.id, {
                        "type": "state_change",
                        "state": session.state.value,
                    })

        return can_use_tool

    async def respond_to_permission(
        self,
        session_id: str,
        request_id: str,
        allow: bool,
        modified_input: dict | None = None,
        reason: str | None = None,
    ) -> bool:
        """Respond to a pending permission request."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if not session.pending_permission:
            return False

        if session.pending_permission.request_id != request_id:
            return False

        if not session._permission_response:
            return False

        if allow:
            result = {
                "behavior": "allow",
                "updated_input": modified_input,
            }
        else:
            result = {
                "behavior": "deny",
                "message": reason or "User denied permission",
            }

        session._permission_response.set_result(result)

        await self._broadcast_to_session(session_id, {
            "type": "permission_response",
            "request_id": request_id,
            "allowed": allow,
        })

        return True

    async def interrupt_session(self, session_id: str) -> bool:
        """Interrupt a running session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if session.state not in (
            SessionState.THINKING,
            SessionState.TOOL_EXECUTING,
            SessionState.PERMISSION_PENDING,
        ):
            return False

        session.state = SessionState.INTERRUPTED

        # Cancel permission wait
        if session._permission_response and not session._permission_response.done():
            session._permission_response.set_result({
                "behavior": "deny",
                "message": "Session interrupted",
                "interrupt": True,
            })

        # Cancel task
        if session._task and not session._task.done():
            session._task.cancel()

        # Interrupt client
        if session._client:
            try:
                await session._client.interrupt()
            except Exception:
                pass

        await self._broadcast_to_session(session_id, {
            "type": "interrupted",
        })

        return True

    async def update_session(
        self,
        session_id: str,
        name: str | None = None,
        model: str | None = None,
        permission_mode: str | None = None,
        thinking_mode: str | None = None,
        budget_usd: float | None = None,
        system_prompt: str | None = None,
    ) -> Session | None:
        """Update session settings."""
        session = self.sessions.get(session_id)
        if not session:
            return None

        if name:
            session.name = name
        if model:
            session.model = model
        if permission_mode:
            session.permission_mode = permission_mode
        if thinking_mode and thinking_mode in THINKING_BUDGETS:
            session.thinking_mode = thinking_mode
        if budget_usd is not None:
            session.budget_usd = budget_usd if budget_usd > 0 else None
        if system_prompt is not None:
            session.system_prompt = system_prompt if system_prompt else None

        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "session_updated",
            "session": session.to_dict(),
        })

        return session

    async def set_thinking_mode(self, session_id: str, mode: str) -> bool:
        """Set thinking mode for a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if mode not in THINKING_BUDGETS:
            return False

        session.thinking_mode = mode
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "thinking_mode_changed",
            "mode": mode,
        })

        return True

    async def set_plan_mode(self, session_id: str, enabled: bool) -> bool:
        """Enable or disable plan mode for a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.plan_mode_active = enabled
        if not enabled:
            session.proposed_plan = None
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "plan_mode_changed",
            "enabled": enabled,
        })

        return True

    async def approve_plan(self, session_id: str) -> bool:
        """Approve the proposed plan and exit plan mode."""
        session = self.sessions.get(session_id)
        if not session or not session.plan_mode_active:
            return False

        # Exit plan mode (keep the proposed plan for reference)
        session.plan_mode_active = False
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "plan_approved",
            "plan": session.proposed_plan,
        })

        await self._broadcast_to_session(session_id, {
            "type": "plan_mode_changed",
            "enabled": False,
        })

        return True

    async def set_model(self, session_id: str, model_id: str) -> bool:
        """Change the model for a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.model = model_id
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "model_changed",
            "model": model_id,
        })

        return True

    async def set_budget(self, session_id: str, budget_usd: float | None) -> bool:
        """Set budget limit for a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.budget_usd = budget_usd
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "budget_changed",
            "budget_usd": budget_usd,
        })

        return True

    # === DeepAgents Methods ===

    async def _process_deepagents_conversation(
        self,
        session: Session,
        prompt: str,
        system_prompt: str | None = None,
    ):
        """Process conversation with DeepAgents engine."""
        session.state = SessionState.THINKING
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session.id, {
            "type": "state_change",
            "state": session.state.value,
        })

        try:
            from deepagents import create_deep_agent
            from langchain_anthropic import ChatAnthropic

            # Create model
            model = ChatAnthropic(
                model=session.model,
                temperature=0.7,
            )

            # Build system prompt
            effective_system_prompt = system_prompt or session.system_prompt or ""

            # Add loaded skills to system prompt
            if session.loaded_skills:
                skill_prompts = await self._load_skill_prompts(session)
                if skill_prompts:
                    effective_system_prompt = f"{effective_system_prompt}\n\n{skill_prompts}"

            # Create DeepAgents agent
            agent = create_deep_agent(
                model=model,
                system_prompt=effective_system_prompt,
            )
            session._deepagent = agent

            # Build messages history
            messages = []
            for msg in session.messages:
                if msg.role == MessageRole.USER:
                    for block in msg.content:
                        if block.type == "text":
                            messages.append({"role": "user", "content": block.content})
                elif msg.role == MessageRole.ASSISTANT:
                    for block in msg.content:
                        if block.type == "text":
                            messages.append({"role": "assistant", "content": block.content})

            # Process with streaming
            current_text = ""
            current_thinking = ""
            current_blocks: list[ContentBlock] = []
            emitted_tools: set[str] = set()

            async for chunk in agent.astream(
                {"messages": messages},
                stream_mode="values",
            ):
                if session.state == SessionState.INTERRUPTED:
                    break

                # Parse LangGraph chunk
                if "messages" in chunk and chunk["messages"]:
                    last_msg = chunk["messages"][-1]

                    # Handle text content
                    if hasattr(last_msg, "content"):
                        content = last_msg.content
                        if isinstance(content, str) and content != current_text:
                            delta = content[len(current_text):]
                            current_text = content
                            if delta:
                                await self._broadcast_to_session(session.id, {
                                    "type": "stream",
                                    "stream_type": "text",
                                    "content": delta,
                                })

                    # Handle tool calls
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        session.state = SessionState.TOOL_EXECUTING
                        await self._broadcast_to_session(session.id, {
                            "type": "state_change",
                            "state": session.state.value,
                        })

                        for tc in last_msg.tool_calls:
                            tool_id = tc.get("id", str(uuid.uuid4())[:8])
                            if tool_id not in emitted_tools:
                                emitted_tools.add(tool_id)
                                tool_name = tc.get("name", "unknown")
                                tool_args = tc.get("args", {})

                                # Track file operations
                                if tool_name in ["write_file", "edit_file", "read_file", "glob", "grep", "execute"]:
                                    file_op = FileOperation(
                                        id=tool_id,
                                        operation=tool_name,
                                        path=tool_args.get("path", tool_args.get("pattern", "")),
                                        content_preview=str(tool_args)[:500],
                                    )
                                    session.file_operations.append(file_op)
                                    await self._broadcast_to_session(session.id, {
                                        "type": "file_operation",
                                        "operation": file_op.to_dict(),
                                    })

                                current_blocks.append(ContentBlock(
                                    type="tool_use",
                                    content=tool_args,
                                    tool_id=tool_id,
                                    tool_name=tool_name,
                                ))

                                await self._broadcast_to_session(session.id, {
                                    "type": "tool_use",
                                    "tool_id": tool_id,
                                    "tool_name": tool_name,
                                    "tool_input": tool_args,
                                })

                    # Handle additional kwargs (thinking)
                    if hasattr(last_msg, "additional_kwargs"):
                        thinking = last_msg.additional_kwargs.get("thinking")
                        if thinking and thinking != current_thinking:
                            delta = thinking[len(current_thinking):]
                            current_thinking = thinking
                            if delta:
                                await self._broadcast_to_session(session.id, {
                                    "type": "stream",
                                    "stream_type": "thinking",
                                    "content": delta,
                                })

                # Handle todos from middleware
                if "todos" in chunk:
                    session.todos = [
                        TodoItem(
                            id=t.get("id", str(uuid.uuid4())[:8]),
                            content=t.get("content", ""),
                            status=t.get("status", "pending"),
                            priority=t.get("priority", 0),
                        )
                        for t in chunk["todos"]
                    ]
                    await self._broadcast_to_session(session.id, {
                        "type": "todos_update",
                        "todos": [t.to_dict() for t in session.todos],
                    })

                # Handle usage info
                if hasattr(chunk, "usage"):
                    usage = chunk.usage
                    if usage:
                        session.input_tokens += usage.get("input_tokens", 0)
                        session.output_tokens += usage.get("output_tokens", 0)
                        await self._broadcast_to_session(session.id, {
                            "type": "token_usage",
                            "input_tokens": session.input_tokens,
                            "output_tokens": session.output_tokens,
                        })

            # Finalize assistant message
            if current_text:
                current_blocks.insert(0, ContentBlock(type="text", content=current_text))
            if current_thinking:
                current_blocks.insert(0, ContentBlock(type="thinking", content=current_thinking))

            if current_blocks:
                assistant_msg = Message(
                    id=str(uuid.uuid4())[:8],
                    role=MessageRole.ASSISTANT,
                    content=current_blocks,
                    metadata={
                        "input_tokens": session.input_tokens,
                        "output_tokens": session.output_tokens,
                    },
                )
                session.messages.append(assistant_msg)

                await self._broadcast_to_session(session.id, {
                    "type": "message",
                    "message": assistant_msg.to_dict(),
                })

            session.state = SessionState.COMPLETED

            await self._broadcast_to_session(session.id, {
                "type": "result",
                "input_tokens": session.input_tokens,
                "output_tokens": session.output_tokens,
            })

        except asyncio.CancelledError:
            session.state = SessionState.INTERRUPTED
            await self._broadcast_to_session(session.id, {
                "type": "interrupted",
            })

        except Exception as e:
            session.state = SessionState.ERROR
            await self._broadcast_to_session(session.id, {
                "type": "error",
                "error": str(e),
            })

        finally:
            session.updated_at = datetime.now()
            session._deepagent = None

            await self._broadcast_to_session(session.id, {
                "type": "state_change",
                "state": session.state.value,
            })

    async def _load_skill_prompts(self, session: Session) -> str:
        """Load skill prompts for loaded skills."""
        prompts = []
        for skill_name in session.loaded_skills:
            skill_path = Path(session.cwd) / ".arche" / "skills" / skill_name / "skill.yaml"
            if skill_path.exists():
                try:
                    import yaml
                    with open(skill_path) as f:
                        skill_data = yaml.safe_load(f)
                    if skill_data and skill_data.get("system_prompt"):
                        prompts.append(f"# Skill: {skill_name}\n{skill_data['system_prompt']}")
                except Exception:
                    pass
        return "\n\n".join(prompts)

    async def update_todos(self, session_id: str, todos: list[dict]) -> bool:
        """Update session todos and broadcast."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.todos = [
            TodoItem(
                id=t.get("id", str(uuid.uuid4())[:8]),
                content=t.get("content", ""),
                status=t.get("status", "pending"),
                priority=t.get("priority", 0),
            )
            for t in todos
        ]
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "todos_update",
            "todos": [t.to_dict() for t in session.todos],
        })

        return True

    async def add_todo(self, session_id: str, content: str, priority: int = 0) -> TodoItem | None:
        """Add a new todo item."""
        session = self.sessions.get(session_id)
        if not session:
            return None

        todo = TodoItem(
            id=str(uuid.uuid4())[:8],
            content=content,
            status="pending",
            priority=priority,
        )
        session.todos.append(todo)
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "todos_update",
            "todos": [t.to_dict() for t in session.todos],
        })

        return todo

    async def update_todo_status(self, session_id: str, todo_id: str, status: str) -> bool:
        """Update a todo item's status."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        for todo in session.todos:
            if todo.id == todo_id:
                todo.status = status
                if status == "completed":
                    todo.completed_at = datetime.now()
                break
        else:
            return False

        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "todos_update",
            "todos": [t.to_dict() for t in session.todos],
        })

        return True

    async def delete_todo(self, session_id: str, todo_id: str) -> bool:
        """Delete a todo item."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.todos = [t for t in session.todos if t.id != todo_id]
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "todos_update",
            "todos": [t.to_dict() for t in session.todos],
        })

        return True

    async def load_skill(self, session_id: str, skill_name: str) -> bool:
        """Load a skill into the session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if skill_name in session.loaded_skills:
            return True  # Already loaded

        # Verify skill exists
        skill_path = Path(session.cwd) / ".arche" / "skills" / skill_name / "skill.yaml"
        if not skill_path.exists():
            return False

        session.loaded_skills.append(skill_name)
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "skill_loaded",
            "skill_name": skill_name,
            "loaded_skills": session.loaded_skills,
        })

        return True

    async def unload_skill(self, session_id: str, skill_name: str) -> bool:
        """Unload a skill from the session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if skill_name not in session.loaded_skills:
            return False

        session.loaded_skills.remove(skill_name)
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "skill_unloaded",
            "skill_name": skill_name,
            "loaded_skills": session.loaded_skills,
        })

        return True

    async def set_capabilities(self, session_id: str, capabilities: list[str]) -> bool:
        """Update session capabilities."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.enabled_capabilities = capabilities
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "capabilities_changed",
            "capabilities": capabilities,
        })

        return True

    async def set_engine(self, session_id: str, engine: str) -> bool:
        """Change the engine for a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        if engine not in ("claude_sdk", "deepagents"):
            return False

        session.engine = engine
        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "engine_changed",
            "engine": engine,
        })

        return True

    async def approve_file_operation(self, session_id: str, op_id: str) -> bool:
        """Approve a pending file operation."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        for op in session.file_operations:
            if op.id == op_id:
                op.approved = True
                break
        else:
            return False

        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "file_operation_approved",
            "op_id": op_id,
        })

        return True

    async def reject_file_operation(self, session_id: str, op_id: str, reason: str = "") -> bool:
        """Reject a pending file operation."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        for op in session.file_operations:
            if op.id == op_id:
                op.result = f"Rejected: {reason}" if reason else "Rejected"
                break
        else:
            return False

        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "file_operation_rejected",
            "op_id": op_id,
            "reason": reason,
        })

        return True


# Global session manager instance
session_manager = SessionManager()


# === Claude CLI Session Discovery ===

def get_claude_projects_dir() -> Path:
    """Get Claude CLI projects directory."""
    return Path.home() / ".claude" / "projects"


def get_project_dir_name(cwd: Path) -> str:
    """Convert working directory to Claude project directory name."""
    # Claude CLI uses path with slashes replaced by dashes
    return str(cwd).replace("/", "-")


@dataclass
class ExistingSession:
    """An existing Claude CLI session that can be resumed."""
    session_id: str
    project_path: str
    cwd: str
    git_branch: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int
    first_message_preview: str | None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
            "first_message_preview": self.first_message_preview,
            "is_resumable": True,
        }


def list_existing_sessions(cwd: Path | None = None, limit: int = 50) -> list[ExistingSession]:
    """List existing Claude CLI sessions that can be resumed.

    Args:
        cwd: If provided, only list sessions for this project directory
        limit: Maximum number of sessions to return

    Returns:
        List of existing sessions, sorted by updated_at descending
    """
    projects_dir = get_claude_projects_dir()
    if not projects_dir.exists():
        return []

    sessions: list[ExistingSession] = []

    # Determine which project directories to scan
    if cwd:
        project_name = get_project_dir_name(cwd)
        project_dirs = [projects_dir / project_name]
    else:
        project_dirs = [d for d in projects_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]

    for project_dir in project_dirs:
        if not project_dir.exists():
            continue

        # List all .jsonl session files
        for session_file in project_dir.glob("*.jsonl"):
            try:
                session_id = session_file.stem  # UUID without extension

                # Get file timestamps
                stat = session_file.stat()
                created_at = datetime.fromtimestamp(stat.st_ctime)
                updated_at = datetime.fromtimestamp(stat.st_mtime)

                # Parse first few lines to get metadata
                cwd_str = ""
                git_branch = None
                message_count = 0
                first_message_preview = None

                with open(session_file, 'r') as f:
                    for i, line in enumerate(f):
                        if i > 20:  # Only scan first 20 lines for metadata
                            break
                        try:
                            data = json.loads(line)
                            if data.get("type") == "user" and "cwd" in data:
                                cwd_str = data.get("cwd", "")
                                git_branch = data.get("gitBranch")
                                if data.get("message", {}).get("content"):
                                    content = data["message"]["content"]
                                    if isinstance(content, str):
                                        first_message_preview = content[:100]
                                    elif isinstance(content, list) and content:
                                        first_message_preview = str(content[0])[:100]
                            if data.get("type") in ("user", "assistant"):
                                message_count += 1
                        except json.JSONDecodeError:
                            continue

                # Count total messages
                with open(session_file, 'r') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            if data.get("type") in ("user", "assistant"):
                                message_count += 1
                        except json.JSONDecodeError:
                            continue

                # Convert project dir name back to path
                project_path = project_dir.name.replace("-", "/")
                if project_path.startswith("/"):
                    project_path = project_path  # Already absolute

                sessions.append(ExistingSession(
                    session_id=session_id,
                    project_path=project_path,
                    cwd=cwd_str or project_path,
                    git_branch=git_branch,
                    created_at=created_at,
                    updated_at=updated_at,
                    message_count=message_count // 2,  # Rough estimate (user+assistant pairs)
                    first_message_preview=first_message_preview,
                ))

            except Exception:
                continue  # Skip problematic files

    # Sort by updated_at descending and limit
    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    return sessions[:limit]


# === Model Discovery ===

import logging
import requests
from functools import lru_cache
from typing import TypedDict

logger = logging.getLogger(__name__)


class ModelInfo(TypedDict):
    """Model information from API."""
    id: str
    name: str
    display_name: str
    created_at: str


# Cache for models (TTL managed by caller)
_models_cache: list[ModelInfo] | None = None
_models_cache_time: float = 0
_CACHE_TTL = 300  # 5 minutes


def get_claude_credentials() -> dict | None:
    """Load Claude CLI OAuth credentials."""
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if not creds_path.exists():
        return None
    try:
        with open(creds_path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load credentials: {e}")
        return None


def fetch_models_from_api() -> list[ModelInfo]:
    """Fetch available models from Anthropic API using OAuth token.

    Uses the oauth-2025-04-20 beta flag to authenticate with OAuth token.
    See docs/anthropic-oauth-api.md for details.
    """
    creds = get_claude_credentials()
    if not creds:
        logger.warning("No Claude credentials found")
        return []

    token = creds.get("claudeAiOauth", {}).get("accessToken")
    if not token:
        logger.warning("No access token in credentials")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "anthropic-dangerous-direct-browser-access": "true",
    }

    try:
        response = requests.get(
            "https://api.anthropic.com/v1/models",
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for item in data.get("data", []):
            models.append({
                "id": item.get("id", ""),
                "name": item.get("id", ""),  # Use ID as name
                "display_name": item.get("display_name", item.get("id", "")),
                "created_at": item.get("created_at", ""),
            })

        logger.info(f"Fetched {len(models)} models from API")
        return models

    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch models from API: {e}")
        return []
    except Exception as e:
        logger.warning(f"Error parsing models response: {e}")
        return []


def get_available_models(force_refresh: bool = False) -> list[dict]:
    """Get list of available Claude models.

    Fetches from API with caching. Falls back to known models if API fails.

    Args:
        force_refresh: Force refresh from API ignoring cache
    """
    import time
    global _models_cache, _models_cache_time

    # Check cache
    now = time.time()
    if not force_refresh and _models_cache and (now - _models_cache_time) < _CACHE_TTL:
        return _models_cache

    # Fetch from API
    models = fetch_models_from_api()

    if models:
        # Sort: newest first (by created_at), then by name
        models.sort(key=lambda m: (m.get("created_at", ""), m.get("id", "")), reverse=True)

        # Add recommended flag (latest sonnet)
        for model in models:
            model["recommended"] = "sonnet-4-5" in model["id"]

        _models_cache = models
        _models_cache_time = now
        return models

    # Fallback to cached if API fails
    if _models_cache:
        return _models_cache

    # Ultimate fallback: hardcoded models
    logger.warning("Using fallback hardcoded models")
    return [
        {"id": "claude-sonnet-4-5-20250929", "name": "claude-sonnet-4-5-20250929", "display_name": "Claude Sonnet 4.5", "recommended": True},
        {"id": "claude-opus-4-5-20251101", "name": "claude-opus-4-5-20251101", "display_name": "Claude Opus 4.5", "recommended": False},
        {"id": "claude-haiku-4-5-20251001", "name": "claude-haiku-4-5-20251001", "display_name": "Claude Haiku 4.5", "recommended": False},
    ]


def get_default_model() -> str:
    """Get the default model ID."""
    models = get_available_models()
    for model in models:
        if model.get("recommended"):
            return model["id"]
    return models[0]["id"] if models else "claude-sonnet-4-5-20250929"
