"""Interactive mode session manager for Claude Code-like experience.

Multi-session management with real-time WebSocket communication,
human-in-the-loop permission handling, and streaming responses.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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


class SessionState(str, Enum):
    """Session lifecycle states."""
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_EXECUTING = "tool_executing"
    PERMISSION_PENDING = "permission_pending"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    ERROR = "error"


class MessageRole(str, Enum):
    """Message roles in conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


@dataclass
class ContentBlock:
    """Content block in a message."""
    type: str  # text, thinking, tool_use, tool_result
    content: Any
    tool_id: str | None = None
    tool_name: str | None = None


@dataclass
class Message:
    """A message in the conversation."""
    id: str
    role: MessageRole
    content: list[ContentBlock]
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role.value,
            "content": [
                {
                    "type": c.type,
                    "content": c.content,
                    "tool_id": c.tool_id,
                    "tool_name": c.tool_name,
                }
                for c in self.content
            ],
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PermissionRequest:
    """A pending permission request."""
    request_id: str
    tool_name: str
    tool_input: dict[str, Any]
    suggestions: list[dict] | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "suggestions": self.suggestions,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Session:
    """An interactive Claude session."""
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

    # Conversation
    messages: list[Message] = field(default_factory=list)

    # Execution state
    current_turn: int = 0
    total_cost_usd: float = 0.0
    pending_permission: PermissionRequest | None = None

    # Internal
    _client: ClaudeSDKClient | None = field(default=None, repr=False)
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
        }
        if include_messages:
            result["messages"] = [m.to_dict() for m in self.messages]
        return result


# Type alias for broadcast callback
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class SessionManager:
    """Manages multiple interactive Claude sessions."""

    def __init__(self, default_cwd: Path | None = None):
        self.sessions: dict[str, Session] = {}
        self.default_cwd = default_cwd or Path.cwd()
        self._broadcast: BroadcastCallback | None = None
        self._lock = asyncio.Lock()

    def set_broadcast_callback(self, callback: BroadcastCallback):
        """Set callback for broadcasting messages to WebSocket clients."""
        self._broadcast = callback

    async def _broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast message to session's WebSocket clients."""
        if self._broadcast:
            await self._broadcast(session_id, message)

    async def create_session(
        self,
        name: str | None = None,
        model: str | None = None,
        cwd: str | None = None,
        permission_mode: str = "default",
        resume: str | None = None,
    ) -> Session:
        """Create a new interactive session or resume an existing one.

        Args:
            name: Session name
            model: Model ID to use
            cwd: Working directory
            permission_mode: Permission mode (default, acceptEdits, plan, bypassPermissions)
            resume: Session ID from Claude CLI to resume
        """
        session_id = str(uuid.uuid4())[:8]

        # Generate name based on resume status
        if resume:
            session_name = name or f"Resumed: {resume[:8]}"
        else:
            session_name = name or f"Session {len(self.sessions) + 1}"

        session = Session(
            id=session_id,
            name=session_name,
            model=model or "claude-sonnet-4-20250514",
            cwd=cwd or str(self.default_cwd),
            permission_mode=permission_mode,
            resume_session_id=resume,
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

        # Start processing in background
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

            if system_prompt:
                opts["system_prompt"] = system_prompt

            # For interactive mode, we need human-in-the-loop
            if session.permission_mode != "bypassPermissions":
                opts["permission_mode"] = session.permission_mode
                opts["can_use_tool"] = self._create_permission_callback(session)
            else:
                opts["permission_mode"] = "bypassPermissions"

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

        session.updated_at = datetime.now()

        await self._broadcast_to_session(session_id, {
            "type": "session_updated",
            "session": session.to_dict(),
        })

        return session


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

# Known Claude models with their details
CLAUDE_MODELS = [
    {
        "id": "claude-sonnet-4-20250514",
        "name": "Claude Sonnet 4",
        "description": "Latest Sonnet model - fast and capable",
        "context_window": 200000,
        "recommended": True,
    },
    {
        "id": "claude-opus-4-20250514",
        "name": "Claude Opus 4",
        "description": "Most capable model - best for complex tasks",
        "context_window": 200000,
        "recommended": False,
    },
    {
        "id": "claude-3-7-sonnet-20250219",
        "name": "Claude 3.7 Sonnet",
        "description": "Extended thinking model",
        "context_window": 200000,
        "recommended": False,
    },
    {
        "id": "claude-3-5-sonnet-20241022",
        "name": "Claude 3.5 Sonnet",
        "description": "Previous generation Sonnet",
        "context_window": 200000,
        "recommended": False,
    },
    {
        "id": "claude-3-5-haiku-20241022",
        "name": "Claude 3.5 Haiku",
        "description": "Fastest model - good for simple tasks",
        "context_window": 200000,
        "recommended": False,
    },
]


def get_available_models() -> list[dict]:
    """Get list of available Claude models.

    Returns models that are known to work with Claude Code.
    """
    return CLAUDE_MODELS


def get_default_model() -> str:
    """Get the default model ID."""
    for model in CLAUDE_MODELS:
        if model.get("recommended"):
            return model["id"]
    return CLAUDE_MODELS[0]["id"] if CLAUDE_MODELS else "claude-sonnet-4-20250514"
