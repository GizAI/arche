"""Core module - shared models, domain types, and infrastructure.

This module provides the foundation for the arche codebase:
- DataModel: Base class for all data models with automatic serialization
- Domain types: TodoItem, FileOperation, SkillInfo, etc.
- EventBus: Centralized event publishing and subscription
- Strategy patterns: Engine selection, Permission handling
"""

from .models import DataModel, TimestampedModel
from .domain import (
    # Enums
    SessionState,
    MessageRole,
    EngineType,
    AgentCapability,
    TaskStatus,
    # Data models
    TodoItem,
    SubAgentTask,
    FileOperation,
    SkillInfo,
    ContentBlock,
    Message,
    PermissionRequest,
)
from .events import SessionEvent, EventBus, event_bus, BroadcastCallback
from .engines import ConversationEngine, EngineRegistry, EngineConfig, engine_registry
from .permissions import (
    PermissionStrategy,
    PermissionStrategyFactory,
    PermissionResult,
    PlanModePermission,
    BypassPermission,
    InteractivePermission,
)

__all__ = [
    # Base models
    "DataModel",
    "TimestampedModel",
    # Enums
    "SessionState",
    "MessageRole",
    "EngineType",
    "AgentCapability",
    "TaskStatus",
    # Domain models
    "TodoItem",
    "SubAgentTask",
    "FileOperation",
    "SkillInfo",
    "ContentBlock",
    "Message",
    "PermissionRequest",
    # Events
    "SessionEvent",
    "EventBus",
    "event_bus",
    "BroadcastCallback",
    # Engine Strategy
    "ConversationEngine",
    "EngineRegistry",
    "EngineConfig",
    "engine_registry",
    # Permission Strategy
    "PermissionStrategy",
    "PermissionStrategyFactory",
    "PermissionResult",
    "PlanModePermission",
    "BypassPermission",
    "InteractivePermission",
]
