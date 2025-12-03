"""Engine Strategy pattern for conversation processing.

Defines the protocol for conversation engines and provides a registry
for selecting engines at runtime.

Currently supported engines:
- claude_sdk: Native Claude SDK with ClaudeSDKClient
- deepagents: LangGraph-based DeepAgents with middleware support
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid circular imports
    pass


class ConversationEngine(Protocol):
    """Protocol for conversation engines.

    Each engine implements its own strategy for processing conversations,
    handling tools, and streaming responses.
    """

    @property
    def name(self) -> str:
        """Engine identifier."""
        ...

    @property
    def supports_streaming(self) -> bool:
        """Whether this engine supports real-time streaming."""
        ...

    @property
    def supports_tools(self) -> bool:
        """Whether this engine supports tool use."""
        ...

    async def process(
        self,
        session: Any,  # Session type from interactive.py
        prompt: str,
        system_prompt: str | None = None,
        broadcast_callback: Any = None,
    ) -> None:
        """Process a conversation turn.

        Args:
            session: The session object with state and history
            prompt: User's input message
            system_prompt: Optional system prompt override
            broadcast_callback: Async callback for broadcasting events
        """
        ...


class EngineRegistry:
    """Registry for conversation engines.

    Allows dynamic registration and lookup of engines by name.

    Example:
        registry = EngineRegistry()
        registry.register("custom", CustomEngine())

        engine = registry.get("custom")
        await engine.process(session, prompt)
    """

    def __init__(self):
        self._engines: dict[str, ConversationEngine] = {}
        self._default: str | None = None

    def register(self, name: str, engine: ConversationEngine, default: bool = False) -> None:
        """Register an engine.

        Args:
            name: Engine name/identifier
            engine: Engine instance
            default: Set as default engine
        """
        self._engines[name] = engine
        if default or self._default is None:
            self._default = name

    def get(self, name: str | None = None) -> ConversationEngine | None:
        """Get an engine by name.

        Args:
            name: Engine name, or None for default

        Returns:
            Engine instance or None if not found
        """
        if name is None:
            name = self._default
        return self._engines.get(name) if name else None

    def available(self) -> list[str]:
        """List available engine names."""
        return list(self._engines.keys())

    @property
    def default(self) -> str | None:
        """Default engine name."""
        return self._default


# Global engine registry
engine_registry = EngineRegistry()


# === Engine Configuration ===

class EngineConfig:
    """Configuration for engine options.

    Centralizes engine-specific configuration that was previously
    scattered in if-else branches.
    """

    def __init__(
        self,
        model: str | None = None,
        cwd: str | None = None,
        system_prompt: str | None = None,
        thinking_mode: str = "normal",
        thinking_budget: int | None = None,
        max_budget_usd: float | None = None,
        permission_mode: str = "default",
        resume_session_id: str | None = None,
        allowed_tools: list[str] | None = None,
    ):
        self.model = model
        self.cwd = cwd
        self.system_prompt = system_prompt
        self.thinking_mode = thinking_mode
        self.thinking_budget = thinking_budget
        self.max_budget_usd = max_budget_usd
        self.permission_mode = permission_mode
        self.resume_session_id = resume_session_id
        self.allowed_tools = allowed_tools

    @classmethod
    def from_session(cls, session: Any) -> "EngineConfig":
        """Create config from session state.

        Args:
            session: Session object

        Returns:
            EngineConfig with session's settings
        """
        from arche.core.domain import THINKING_BUDGETS

        thinking_budget = None
        if session.thinking_mode != "normal":
            thinking_budget = THINKING_BUDGETS.get(session.thinking_mode)

        return cls(
            model=session.model,
            cwd=session.cwd,
            system_prompt=session.system_prompt,
            thinking_mode=session.thinking_mode,
            thinking_budget=thinking_budget,
            max_budget_usd=session.budget_usd,
            permission_mode=session.permission_mode,
            resume_session_id=session.resume_session_id,
        )

    def to_sdk_options(self) -> dict[str, Any]:
        """Convert to Claude SDK options dict."""
        opts: dict[str, Any] = {
            "include_partial_messages": True,
        }

        if self.cwd:
            opts["cwd"] = self.cwd
        if self.model:
            opts["model"] = self.model
        if self.system_prompt:
            opts["system_prompt"] = self.system_prompt
        if self.thinking_budget:
            opts["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
        if self.max_budget_usd:
            opts["max_budget_usd"] = self.max_budget_usd
        if self.resume_session_id:
            opts["resume"] = self.resume_session_id
        if self.allowed_tools:
            opts["allowed_tools"] = self.allowed_tools

        return opts
