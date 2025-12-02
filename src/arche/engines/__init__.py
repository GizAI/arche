"""Arche AI Agent Engines.

Provides swappable AI execution engines:
- claude_sdk: Claude Agent SDK (default)
- deepagents: DeepAgents/LangGraph
- codex: OpenAI Codex SDK (placeholder)
"""

from .base import AgentEngine, AgentEvent, AgentState, AgentStatus, EventType


def create_engine(engine_type: str = "claude_sdk", **kwargs) -> AgentEngine:
    """Factory function to create an agent engine.

    Args:
        engine_type: 'claude_sdk', 'deepagents', or 'codex'
        **kwargs: Engine-specific arguments

    Returns:
        AgentEngine instance
    """
    if engine_type == "claude_sdk":
        from .claude_sdk import ClaudeSDKEngine
        return ClaudeSDKEngine(**kwargs)

    if engine_type == "deepagents":
        from .deepagents import DeepAgentsEngine
        return DeepAgentsEngine(**kwargs)

    if engine_type == "codex":
        from .codex import CodexEngine
        return CodexEngine(**kwargs)

    raise ValueError(f"Unknown engine type: {engine_type}. Use: claude_sdk, deepagents, codex")


__all__ = [
    "AgentEngine",
    "AgentEvent",
    "AgentState",
    "AgentStatus",
    "EventType",
    "create_engine",
]
