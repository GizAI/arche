"""WebSocket message command handlers using Command pattern.

Replaces 21+ elif branches in app.py WebSocket handler with
a registry of command classes.

Each command implements the MessageCommand protocol and is
registered with the COMMANDS dictionary.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket


class MessageCommand(Protocol):
    """Protocol for WebSocket message handlers."""

    async def execute(
        self,
        session_id: str,
        data: dict[str, Any],
        context: "CommandContext",
    ) -> None:
        """Execute the command.

        Args:
            session_id: The session ID this message is for
            data: The message data from the client
            context: Command execution context with managers
        """
        ...


@dataclass
class CommandContext:
    """Context for command execution.

    Provides access to all managers needed by commands.
    """
    session_manager: Any
    background_task_manager: Any
    checkpoint_manager: Any
    mcp_server_manager: Any
    hooks_manager: Any
    websocket: "WebSocket | None" = None


# === Session Commands ===

class SendMessageCommand:
    """Send a message to the AI."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        content = data.get("content", "")
        system_prompt = data.get("system_prompt")
        if content:
            await context.session_manager.send_message(session_id, content, system_prompt)


class InterruptCommand:
    """Interrupt the current session."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        await context.session_manager.interrupt_session(session_id)


class PermissionResponseCommand:
    """Respond to a permission request."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        await context.session_manager.respond_to_permission(
            session_id,
            data.get("request_id", ""),
            data.get("allow", False),
            modified_input=data.get("modified_input"),
            reason=data.get("reason"),
        )


# === Todo Commands ===

class UpdateTodoCommand:
    """Update a todo item's status."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        todo_id = data.get("todo_id")
        status = data.get("status")
        if todo_id and status:
            await context.session_manager.update_todo_status(session_id, todo_id, status)


class AddTodoCommand:
    """Add a new todo item."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        content = data.get("content", "")
        priority = data.get("priority", 0)
        if content:
            await context.session_manager.add_todo(session_id, content, priority)


class DeleteTodoCommand:
    """Delete a todo item."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        todo_id = data.get("todo_id")
        if todo_id:
            await context.session_manager.delete_todo(session_id, todo_id)


# === Skill Commands ===

class LoadSkillCommand:
    """Load a skill into the session."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        skill_name = data.get("skill_name")
        if skill_name:
            await context.session_manager.load_skill(session_id, skill_name)


class UnloadSkillCommand:
    """Unload a skill from the session."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        skill_name = data.get("skill_name")
        if skill_name:
            await context.session_manager.unload_skill(session_id, skill_name)


# === Engine Commands ===

class SetEngineCommand:
    """Change session engine."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        engine = data.get("engine")
        if engine:
            await context.session_manager.set_engine(session_id, engine)


class SetCapabilitiesCommand:
    """Update session capabilities."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        capabilities = data.get("capabilities", [])
        await context.session_manager.set_capabilities(session_id, capabilities)


# === File Operation Commands ===

class ApproveFileOpCommand:
    """Approve a file operation."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        op_id = data.get("op_id")
        if op_id:
            await context.session_manager.approve_file_operation(session_id, op_id)


class RejectFileOpCommand:
    """Reject a file operation."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        op_id = data.get("op_id")
        reason = data.get("reason", "")
        if op_id:
            await context.session_manager.reject_file_operation(session_id, op_id, reason)


# === Mode Commands ===

class SetThinkingModeCommand:
    """Set the thinking mode."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        mode = data.get("mode")
        if mode:
            await context.session_manager.set_thinking_mode(session_id, mode)


class SetPlanModeCommand:
    """Enable or disable plan mode."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        enabled = data.get("enabled", False)
        await context.session_manager.set_plan_mode(session_id, enabled)


class ApprovePlanCommand:
    """Approve a proposed plan."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        await context.session_manager.approve_plan(session_id)


class SetModelCommand:
    """Set the model for the session."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        model = data.get("model")
        if model:
            await context.session_manager.set_model(session_id, model)


class SetBudgetCommand:
    """Set the budget for the session."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        budget = data.get("budget_usd")
        await context.session_manager.set_budget(session_id, budget)


# === Background Task Commands ===

class RunBackgroundCommand:
    """Run a background task."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        command = data.get("command")
        timeout = data.get("timeout")
        if command:
            session = context.session_manager.get_session(session_id)
            if session:
                await context.background_task_manager.start_task(
                    session_id=session_id,
                    command=command,
                    cwd=session.cwd,
                    timeout=timeout,
                )


class CancelBackgroundCommand:
    """Cancel a background task."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        task_id = data.get("task_id")
        if task_id:
            await context.background_task_manager.cancel_task(task_id)


# === Checkpoint Commands ===

class CreateCheckpointCommand:
    """Create a checkpoint."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        name = data.get("name", "checkpoint")
        description = data.get("description")
        session = context.session_manager.get_session(session_id)
        if session:
            await context.checkpoint_manager.create_checkpoint(
                session_id=session_id,
                name=name,
                description=description,
                cwd=Path(session.cwd),
            )


class RestoreCheckpointCommand:
    """Restore a checkpoint."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        checkpoint_id = data.get("checkpoint_id")
        session = context.session_manager.get_session(session_id)
        if checkpoint_id and session:
            await context.checkpoint_manager.restore_checkpoint(
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                cwd=Path(session.cwd),
            )


# === Utility Commands ===

class PingCommand:
    """Respond to ping with pong."""

    async def execute(self, session_id: str, data: dict, context: CommandContext) -> None:
        if context.websocket:
            await context.websocket.send_json({"type": "pong"})


# === Command Registry ===

COMMANDS: dict[str, MessageCommand] = {
    # Session commands
    "send_message": SendMessageCommand(),
    "interrupt": InterruptCommand(),
    "permission_response": PermissionResponseCommand(),

    # Todo commands
    "update_todo": UpdateTodoCommand(),
    "add_todo": AddTodoCommand(),
    "delete_todo": DeleteTodoCommand(),

    # Skill commands
    "load_skill": LoadSkillCommand(),
    "unload_skill": UnloadSkillCommand(),

    # Engine commands
    "set_engine": SetEngineCommand(),
    "set_capabilities": SetCapabilitiesCommand(),

    # File operation commands
    "approve_file_op": ApproveFileOpCommand(),
    "reject_file_op": RejectFileOpCommand(),

    # Mode commands
    "set_thinking_mode": SetThinkingModeCommand(),
    "set_plan_mode": SetPlanModeCommand(),
    "approve_plan": ApprovePlanCommand(),
    "set_model": SetModelCommand(),
    "set_budget": SetBudgetCommand(),

    # Background task commands
    "run_background": RunBackgroundCommand(),
    "cancel_background": CancelBackgroundCommand(),

    # Checkpoint commands
    "create_checkpoint": CreateCheckpointCommand(),
    "restore_checkpoint": RestoreCheckpointCommand(),

    # Utility commands
    "ping": PingCommand(),
}


async def handle_websocket_message(
    msg_type: str,
    session_id: str,
    data: dict[str, Any],
    context: CommandContext,
) -> bool:
    """Handle a WebSocket message using the command registry.

    Args:
        msg_type: The message type
        session_id: The session ID
        data: The message data
        context: Command execution context

    Returns:
        True if command was found and executed, False otherwise
    """
    command = COMMANDS.get(msg_type)
    if command:
        await command.execute(session_id, data, context)
        return True
    return False
