"""Base classes for AI Agent engines."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator


class EventType(str, Enum):
    """Types of events emitted during agent execution."""
    CONTENT = "content"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    ERROR = "error"
    COMPLETE = "complete"
    STATUS = "status"


class AgentStatus(str, Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentEvent:
    """Event emitted during agent execution."""
    type: EventType
    content: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentState:
    """State of a running agent."""
    agent_id: str
    status: AgentStatus = AgentStatus.PENDING
    goal: str = ""
    output: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class AgentEngine(ABC):
    """Abstract base class for AI agent engines."""

    @abstractmethod
    async def run(
        self,
        goal: str,
        system_prompt: str,
        tools: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute an agent with the given goal.

        Args:
            goal: The goal/task for the agent
            system_prompt: System prompt defining agent behavior
            tools: Optional list of tools available to the agent

        Yields:
            AgentEvent objects as the agent executes
        """
        pass

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel the running agent."""
        pass

    @abstractmethod
    def get_output(self) -> str:
        """Get accumulated text output."""
        pass
