"""Unified domain models for arche.

Consolidates duplicate dataclasses from:
- interactive.py: TodoItem, FileOperation, etc.
- storage.py: SavedTodo, SavedFileOperation, etc.
- skills.py: SkillInfo, SkillDefinition

These models are the single source of truth for domain types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .models import DataModel, TimestampedModel


# === Enums ===

class EngineType(str, Enum):
    """Available agent engines."""
    CLAUDE_SDK = "claude_sdk"
    DEEPAGENTS = "deepagents"


class AgentCapability(str, Enum):
    """DeepAgents capabilities that can be enabled."""
    FILESYSTEM = "filesystem"
    PLANNING = "planning"
    SUBAGENT = "subagent"
    SUMMARIZATION = "summarization"


class TaskStatus(str, Enum):
    """Status for todos and background tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionState(str, Enum):
    """Session lifecycle states."""
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_EXECUTING = "tool_executing"
    PERMISSION_PENDING = "permission_pending"
    APPROVAL_PENDING = "approval_pending"
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


# === Domain Models ===

@dataclass
class TodoItem(TimestampedModel):
    """Task item from DeepAgents TodoListMiddleware.

    Replaces:
    - interactive.py TodoItem
    - storage.py SavedTodo
    """
    id: str = ""
    content: str = ""
    status: str = "pending"  # pending | in_progress | completed
    priority: int = 0
    completed_at: datetime | None = None


@dataclass
class SubAgentTask(TimestampedModel):
    """SubAgent task delegation."""
    id: str = ""
    goal: str = ""
    status: str = "pending"  # pending | running | completed | failed
    parent_session_id: str = ""
    result: str | None = None
    completed_at: datetime | None = None


@dataclass
class FileOperation(TimestampedModel):
    """File operation record.

    Replaces:
    - interactive.py FileOperation
    - storage.py SavedFileOperation
    """
    id: str = ""
    operation: str = ""  # read | write | edit | glob | grep | execute
    path: str = ""
    content_preview: str | None = None
    diff: str | None = None  # For edit operations
    approved: bool = False
    result: str | None = None
    # Note: TimestampedModel provides created_at, we alias it as timestamp

    @property
    def timestamp(self) -> datetime:
        """Alias for created_at for backward compatibility."""
        return self.created_at


@dataclass
class SkillInfo(DataModel):
    """Skill information.

    Lightweight representation for listing skills.
    Replaces duplicate definitions in interactive.py and skills.py.
    """
    name: str = ""
    description: str = ""
    path: str | None = None  # Path to skill directory
    system_prompt: str | None = None


@dataclass
class ContentBlock(DataModel):
    """Content block in a message."""
    type: str = ""  # text | thinking | tool_use | tool_result
    content: Any = None
    tool_id: str | None = None
    tool_name: str | None = None


@dataclass
class Message(TimestampedModel):
    """A message in the conversation.

    Replaces:
    - interactive.py Message
    - storage.py SavedMessage
    """
    id: str = ""
    role: MessageRole = MessageRole.USER
    content: list[ContentBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Custom serialization for Message."""
        return {
            "id": self.id,
            "role": self.role.value if isinstance(self.role, Enum) else self.role,
            "content": [
                {
                    "type": c.type,
                    "content": c.content,
                    "tool_id": c.tool_id,
                    "tool_name": c.tool_name,
                }
                for c in self.content
            ],
            "timestamp": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PermissionRequest(TimestampedModel):
    """A pending permission request."""
    request_id: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    suggestions: list[dict] | None = None


# === Constants ===

DEFAULT_CAPABILITIES = [
    AgentCapability.FILESYSTEM.value,
    AgentCapability.PLANNING.value,
    AgentCapability.SUBAGENT.value,
    AgentCapability.SUMMARIZATION.value,
]

# Thinking mode budgets (token limits)
THINKING_BUDGETS = {
    "normal": None,
    "think": 10000,
    "think_hard": 50000,
    "ultrathink": 100000,
}

# Plan mode allowed tools (read-only)
PLAN_MODE_TOOLS = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task", "LS", "mcp__*"]
