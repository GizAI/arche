"""Permission Strategy pattern for tool authorization.

Defines strategies for handling tool permissions in different modes:
- PlanMode: Read-only tools only
- Interactive: Human-in-the-loop approval
- AcceptEdits: Auto-approve edits, ask for others
- Bypass: All tools auto-approved

This replaces scattered if-else permission logic with pluggable strategies.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Protocol
from dataclasses import dataclass

from .domain import PLAN_MODE_TOOLS


class PermissionStrategy(Protocol):
    """Protocol for permission handling strategies."""

    @property
    def name(self) -> str:
        """Strategy identifier."""
        ...

    def configure_options(self, opts: dict[str, Any], session: Any) -> None:
        """Configure SDK options for this permission strategy.

        Args:
            opts: Options dict to modify
            session: Session with current state
        """
        ...


class PlanModePermission:
    """Plan mode - read-only tools only.

    Restricts to safe, read-only tools for planning phases.
    """

    @property
    def name(self) -> str:
        return "plan"

    def configure_options(self, opts: dict[str, Any], session: Any) -> None:
        """Configure for plan mode."""
        opts["permission_mode"] = "plan"
        opts["allowed_tools"] = PLAN_MODE_TOOLS


class BypassPermission:
    """Bypass mode - all tools auto-approved.

    For trusted automation or testing scenarios.
    """

    @property
    def name(self) -> str:
        return "bypassPermissions"

    def configure_options(self, opts: dict[str, Any], session: Any) -> None:
        """Configure for bypass mode."""
        opts["permission_mode"] = "bypassPermissions"


class InteractivePermission:
    """Interactive mode - human-in-the-loop approval.

    Requires user approval for tool execution through callbacks.
    """

    def __init__(self, permission_callback_factory: Callable[[Any], Callable] | None = None):
        """Initialize with optional callback factory.

        Args:
            permission_callback_factory: Function that creates permission callbacks
                                        given a session. If None, uses default mode.
        """
        self._callback_factory = permission_callback_factory

    @property
    def name(self) -> str:
        return "default"

    def configure_options(self, opts: dict[str, Any], session: Any) -> None:
        """Configure for interactive mode."""
        opts["permission_mode"] = session.permission_mode
        if self._callback_factory:
            opts["can_use_tool"] = self._callback_factory(session)


class AcceptEditsPermission:
    """Accept edits mode - auto-approve file edits.

    Auto-approves write/edit operations, asks for others.
    """

    def __init__(self, permission_callback_factory: Callable[[Any], Callable] | None = None):
        self._callback_factory = permission_callback_factory

    @property
    def name(self) -> str:
        return "acceptEdits"

    def configure_options(self, opts: dict[str, Any], session: Any) -> None:
        """Configure for accept edits mode."""
        opts["permission_mode"] = "acceptEdits"
        if self._callback_factory:
            opts["can_use_tool"] = self._callback_factory(session)


class PermissionStrategyFactory:
    """Factory for creating permission strategies.

    Selects the appropriate strategy based on session state.

    Example:
        factory = PermissionStrategyFactory(callback_factory)
        strategy = factory.create(session)
        strategy.configure_options(opts, session)
    """

    def __init__(self, permission_callback_factory: Callable[[Any], Callable] | None = None):
        """Initialize factory.

        Args:
            permission_callback_factory: Factory function for creating
                                        permission callbacks
        """
        self._callback_factory = permission_callback_factory

    def create(self, session: Any) -> PermissionStrategy:
        """Create appropriate strategy for session.

        Args:
            session: Session with permission_mode and plan_mode_active

        Returns:
            Appropriate PermissionStrategy instance
        """
        # Plan mode takes priority
        if getattr(session, 'plan_mode_active', False):
            return PlanModePermission()

        # Check permission mode
        mode = getattr(session, 'permission_mode', 'default')

        if mode == "bypassPermissions":
            return BypassPermission()
        elif mode == "acceptEdits":
            return AcceptEditsPermission(self._callback_factory)
        else:
            # default or any other mode
            return InteractivePermission(self._callback_factory)


# === Permission Result Types ===

@dataclass
class PermissionResult:
    """Result of a permission check."""
    approved: bool
    modified_input: dict[str, Any] | None = None
    reason: str | None = None

    def to_sdk_response(self) -> dict[str, Any]:
        """Convert to Claude SDK can_use_tool response format."""
        if self.approved:
            result: dict[str, Any] = {"approved": True}
            if self.modified_input:
                result["input"] = self.modified_input
            return result
        return {
            "approved": False,
            "reason": self.reason or "Permission denied",
        }
