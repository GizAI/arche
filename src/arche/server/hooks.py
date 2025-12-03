"""Hooks system for intercepting tool execution.

Supports PreToolUse, PostToolUse, UserPromptSubmit, and Stop hooks.
Uses centralized EventBus for broadcasting updates.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Awaitable, Any
import logging

from arche.core import event_bus

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    """Types of hooks."""
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    STOP = "stop"
    SUBAGENT_STOP = "subagent_stop"


class HookDecision(str, Enum):
    """Hook decision outcomes."""
    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"


@dataclass
class HookConfig:
    """Configuration for a hook."""
    id: str
    name: str
    type: HookType
    enabled: bool = True
    matcher: str | None = None  # Tool name pattern to match
    command: str | None = None  # Shell command to run
    callback: Callable[..., Awaitable[dict]] | None = None  # Python callback
    timeout: float = 30.0  # Timeout in seconds

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "enabled": self.enabled,
            "matcher": self.matcher,
            "command": self.command,
            "has_callback": self.callback is not None,
            "timeout": self.timeout,
        }


@dataclass
class HookResult:
    """Result from executing a hook."""
    decision: HookDecision = HookDecision.ALLOW
    message: str | None = None
    modified_input: dict | None = None
    suppress_output: bool = False
    stop_reason: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "message": self.message,
            "modified_input": self.modified_input,
            "suppress_output": self.suppress_output,
            "stop_reason": self.stop_reason,
            "metadata": self.metadata,
        }


@dataclass
class HookContext:
    """Context passed to hook handlers."""
    session_id: str
    hook_type: HookType
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: Any = None
    user_prompt: str | None = None
    stop_reason: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "hook_type": self.hook_type.value,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": str(self.tool_output)[:1000] if self.tool_output else None,
            "user_prompt": self.user_prompt[:500] if self.user_prompt else None,
            "stop_reason": self.stop_reason,
            "timestamp": self.timestamp.isoformat(),
        }


# Legacy type alias for backward compatibility
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class HooksManager:
    """Manages and executes hooks.

    Uses centralized EventBus for all broadcasts.
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.cwd() / ".arche"
        self.hooks: dict[str, HookConfig] = {}
        self._lock = asyncio.Lock()

    def set_broadcast_callback(self, callback: BroadcastCallback):
        """Legacy method - broadcasts now go through event_bus."""
        pass

    async def _broadcast_event(self, session_id: str, event_type: str, data: dict):
        """Broadcast hook event via EventBus."""
        await event_bus.broadcast(session_id, {
            "type": event_type,
            **data,
        })

    def register_hook(self, config: HookConfig) -> HookConfig:
        """Register a new hook.

        Args:
            config: Hook configuration

        Returns:
            Registered hook config
        """
        self.hooks[config.id] = config
        return config

    def unregister_hook(self, hook_id: str) -> bool:
        """Unregister a hook by ID."""
        if hook_id in self.hooks:
            del self.hooks[hook_id]
            return True
        return False

    def get_hook(self, hook_id: str) -> HookConfig | None:
        """Get hook by ID."""
        return self.hooks.get(hook_id)

    def list_hooks(self, hook_type: HookType | None = None) -> list[HookConfig]:
        """List all hooks, optionally filtered by type."""
        hooks = list(self.hooks.values())
        if hook_type:
            hooks = [h for h in hooks if h.type == hook_type]
        return hooks

    def set_hook_enabled(self, hook_id: str, enabled: bool) -> bool:
        """Enable or disable a hook."""
        hook = self.hooks.get(hook_id)
        if hook:
            hook.enabled = enabled
            return True
        return False

    def _matches_tool(self, hook: HookConfig, tool_name: str) -> bool:
        """Check if hook matcher matches tool name."""
        if not hook.matcher:
            return True  # No matcher means match all

        import fnmatch
        return fnmatch.fnmatch(tool_name, hook.matcher)

    async def execute_hooks(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookResult:
        """Execute all hooks of a given type.

        Args:
            hook_type: Type of hooks to execute
            context: Hook execution context

        Returns:
            Combined result from all hooks
        """
        result = HookResult()

        # Get matching enabled hooks
        hooks = [
            h for h in self.hooks.values()
            if h.type == hook_type
            and h.enabled
            and (
                not context.tool_name
                or self._matches_tool(h, context.tool_name)
            )
        ]

        if not hooks:
            return result

        for hook in hooks:
            try:
                hook_result = await self._execute_single_hook(hook, context)

                # Merge results (blocking takes precedence)
                if hook_result.decision == HookDecision.BLOCK:
                    result.decision = HookDecision.BLOCK
                    result.message = hook_result.message
                    result.stop_reason = hook_result.stop_reason
                    break  # Stop processing further hooks

                if hook_result.decision == HookDecision.MODIFY:
                    result.decision = HookDecision.MODIFY
                    result.modified_input = hook_result.modified_input

                if hook_result.suppress_output:
                    result.suppress_output = True

                # Merge metadata
                result.metadata.update(hook_result.metadata)

            except Exception as e:
                logger.error(f"Hook {hook.id} failed: {e}")
                # Continue with other hooks

        # Broadcast hook execution result
        await self._broadcast_event(context.session_id, "hook_executed", {
            "hook_type": hook_type.value,
            "tool_name": context.tool_name,
            "result": result.to_dict(),
        })

        return result

    async def _execute_single_hook(
        self,
        hook: HookConfig,
        context: HookContext,
    ) -> HookResult:
        """Execute a single hook."""
        if hook.callback:
            # Python callback
            try:
                raw_result = await asyncio.wait_for(
                    hook.callback(context),
                    timeout=hook.timeout,
                )
                return self._parse_hook_result(raw_result)
            except asyncio.TimeoutError:
                logger.warning(f"Hook {hook.id} timed out")
                return HookResult(message="Hook timed out")

        elif hook.command:
            # Shell command
            return await self._execute_shell_hook(hook, context)

        return HookResult()

    async def _execute_shell_hook(
        self,
        hook: HookConfig,
        context: HookContext,
    ) -> HookResult:
        """Execute a shell command hook."""
        try:
            # Prepare input JSON
            input_data = json.dumps(context.to_dict())

            # Run command with stdin
            process = await asyncio.create_subprocess_shell(
                hook.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input_data.encode('utf-8')),
                    timeout=hook.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return HookResult(message="Hook command timed out")

            if process.returncode != 0:
                logger.warning(f"Hook command failed: {stderr.decode()}")
                return HookResult()

            # Parse output JSON
            try:
                output = json.loads(stdout.decode('utf-8'))
                return self._parse_hook_result(output)
            except json.JSONDecodeError:
                # Non-JSON output is treated as allowing
                return HookResult()

        except Exception as e:
            logger.error(f"Shell hook failed: {e}")
            return HookResult()

    def _parse_hook_result(self, raw: dict | Any) -> HookResult:
        """Parse raw hook output into HookResult."""
        if not isinstance(raw, dict):
            return HookResult()

        decision = HookDecision.ALLOW
        if raw.get("decision") == "block":
            decision = HookDecision.BLOCK
        elif raw.get("decision") == "modify" or raw.get("modified_input"):
            decision = HookDecision.MODIFY

        return HookResult(
            decision=decision,
            message=raw.get("message"),
            modified_input=raw.get("modified_input"),
            suppress_output=raw.get("suppress_output", False),
            stop_reason=raw.get("stop_reason"),
            metadata=raw.get("metadata", {}),
        )

    # Convenience methods for common hook types
    async def pre_tool_use(
        self,
        session_id: str,
        tool_name: str,
        tool_input: dict,
    ) -> HookResult:
        """Execute pre-tool-use hooks."""
        context = HookContext(
            session_id=session_id,
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
        )
        return await self.execute_hooks(HookType.PRE_TOOL_USE, context)

    async def post_tool_use(
        self,
        session_id: str,
        tool_name: str,
        tool_input: dict,
        tool_output: Any,
    ) -> HookResult:
        """Execute post-tool-use hooks."""
        context = HookContext(
            session_id=session_id,
            hook_type=HookType.POST_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        )
        return await self.execute_hooks(HookType.POST_TOOL_USE, context)

    async def user_prompt_submit(
        self,
        session_id: str,
        prompt: str,
    ) -> HookResult:
        """Execute user-prompt-submit hooks."""
        context = HookContext(
            session_id=session_id,
            hook_type=HookType.USER_PROMPT_SUBMIT,
            user_prompt=prompt,
        )
        return await self.execute_hooks(HookType.USER_PROMPT_SUBMIT, context)

    async def on_stop(
        self,
        session_id: str,
        stop_reason: str | None = None,
    ) -> HookResult:
        """Execute stop hooks."""
        context = HookContext(
            session_id=session_id,
            hook_type=HookType.STOP,
            stop_reason=stop_reason,
        )
        return await self.execute_hooks(HookType.STOP, context)

    async def save_config(self):
        """Save hooks configuration to file."""
        config_file = self.config_dir / "hooks.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            hook_id: hook.to_dict()
            for hook_id, hook in self.hooks.items()
            if not hook.callback  # Only save serializable hooks
        }

        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2)

    async def load_config(self):
        """Load hooks configuration from file."""
        config_file = self.config_dir / "hooks.json"
        if not config_file.exists():
            return

        try:
            with open(config_file, 'r') as f:
                data = json.load(f)

            for hook_id, hook_data in data.items():
                config = HookConfig(
                    id=hook_id,
                    name=hook_data["name"],
                    type=HookType(hook_data["type"]),
                    enabled=hook_data.get("enabled", True),
                    matcher=hook_data.get("matcher"),
                    command=hook_data.get("command"),
                    timeout=hook_data.get("timeout", 30.0),
                )
                self.hooks[hook_id] = config

        except Exception as e:
            logger.warning(f"Failed to load hooks config: {e}")


# Global instance
hooks_manager = HooksManager()
