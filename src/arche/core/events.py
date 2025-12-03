"""Centralized event system using Observer pattern.

Consolidates 5 separate BroadcastCallback definitions into one EventBus.
All session-related events flow through this single system.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Awaitable, Any

from .models import DataModel

logger = logging.getLogger(__name__)


@dataclass
class SessionEvent(DataModel):
    """Event emitted for session updates.

    All session-related events (state changes, messages, tool calls, etc.)
    are represented as SessionEvent instances.
    """
    type: str  # Event type: state_change, message, tool_call, permission_request, etc.
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# Type alias for event callbacks
EventCallback = Callable[[SessionEvent], Awaitable[None]]

# Legacy type alias for backward compatibility
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class EventBus:
    """Central event bus for session events.

    Replaces multiple broadcast callback patterns:
    - SessionManager._broadcast_to_session()
    - BackgroundTaskManager._broadcast()
    - CheckpointManager._broadcast()
    - etc.

    Usage:
        # Subscribe to events
        event_bus.subscribe("session_123", my_callback)

        # Publish events
        await event_bus.publish(SessionEvent(
            type="state_change",
            session_id="session_123",
            data={"old_state": "idle", "new_state": "thinking"}
        ))

        # Or use legacy broadcast format
        await event_bus.broadcast("session_123", {"type": "message", ...})
    """

    def __init__(self):
        self._subscribers: dict[str, list[EventCallback]] = {}
        self._global_subscribers: list[EventCallback] = []
        self._legacy_callback: BroadcastCallback | None = None
        self._lock = asyncio.Lock()

    def set_legacy_callback(self, callback: BroadcastCallback) -> None:
        """Set legacy broadcast callback for backward compatibility.

        This allows gradual migration from the old broadcast pattern.
        """
        self._legacy_callback = callback

    async def publish(self, event: SessionEvent) -> None:
        """Publish an event to all subscribers.

        Args:
            event: The session event to publish
        """
        callbacks = []

        async with self._lock:
            # Session-specific subscribers
            callbacks.extend(self._subscribers.get(event.session_id, []))
            # Global subscribers
            callbacks.extend(self._global_subscribers)

        # Call all subscribers
        for callback in callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}", exc_info=True)

        # Legacy callback support
        if self._legacy_callback:
            try:
                await self._legacy_callback(event.session_id, {
                    "type": event.type,
                    **event.data,
                    "timestamp": event.timestamp.isoformat(),
                })
            except Exception as e:
                logger.error(f"Legacy callback error: {e}", exc_info=True)

    async def broadcast(self, session_id: str, message: dict) -> None:
        """Legacy broadcast method for backward compatibility.

        Converts the old-style broadcast to a SessionEvent and publishes it.

        Args:
            session_id: Target session ID
            message: Message dict with 'type' and other data
        """
        event_type = message.pop("type", "unknown")
        await self.publish(SessionEvent(
            type=event_type,
            session_id=session_id,
            data=message,
        ))

    def subscribe(self, session_id: str, callback: EventCallback) -> Callable[[], None]:
        """Subscribe to events for a specific session.

        Args:
            session_id: Session to subscribe to
            callback: Async callback function

        Returns:
            Unsubscribe function
        """
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(callback)

        def unsubscribe():
            if session_id in self._subscribers:
                try:
                    self._subscribers[session_id].remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def subscribe_global(self, callback: EventCallback) -> Callable[[], None]:
        """Subscribe to all events across all sessions.

        Args:
            callback: Async callback function

        Returns:
            Unsubscribe function
        """
        self._global_subscribers.append(callback)

        def unsubscribe():
            try:
                self._global_subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    async def unsubscribe_session(self, session_id: str) -> None:
        """Remove all subscribers for a session.

        Args:
            session_id: Session to unsubscribe from
        """
        async with self._lock:
            if session_id in self._subscribers:
                del self._subscribers[session_id]

    def subscriber_count(self, session_id: str | None = None) -> int:
        """Get the number of subscribers.

        Args:
            session_id: If provided, count for specific session; otherwise total

        Returns:
            Number of subscribers
        """
        if session_id:
            return len(self._subscribers.get(session_id, []))
        return sum(len(subs) for subs in self._subscribers.values()) + len(self._global_subscribers)


# Global event bus instance
event_bus = EventBus()
