"""Background task manager for running commands asynchronously.

Supports running shell commands in the background with real-time output streaming.
Uses centralized EventBus for broadcasting updates.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable, Any

import logging

from arche.core import TaskStatus, event_bus, SessionEvent

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTask:
    """A background task running a shell command."""
    id: str
    session_id: str
    command: str
    cwd: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    output_lines: list[str] = field(default_factory=list)
    error_message: str | None = None

    # Internal
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "exit_code": self.exit_code,
            "output_line_count": len(self.output_lines),
            "error_message": self.error_message,
        }


# Legacy type alias for backward compatibility
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class BackgroundTaskManager:
    """Manages background tasks for interactive sessions.

    Uses centralized EventBus for all broadcasts.
    """

    def __init__(self):
        self.tasks: dict[str, BackgroundTask] = {}
        self._lock = asyncio.Lock()

    def set_broadcast_callback(self, callback: BroadcastCallback):
        """Legacy method - broadcasts now go through event_bus."""
        # No-op: event_bus handles broadcasting via its legacy callback
        pass

    async def _broadcast_update(self, task: BackgroundTask):
        """Broadcast task update to session via EventBus."""
        await event_bus.broadcast(task.session_id, {
            "type": "background_task_update",
            "task": task.to_dict(),
        })

    async def _broadcast_output(self, task: BackgroundTask, line: str):
        """Broadcast new output line to session via EventBus."""
        await event_bus.broadcast(task.session_id, {
            "type": "background_task_output",
            "task_id": task.id,
            "line": line,
            "line_number": len(task.output_lines),
        })

    async def start_task(
        self,
        session_id: str,
        command: str,
        cwd: str | Path | None = None,
        timeout: float | None = None,
    ) -> BackgroundTask:
        """Start a new background task.

        Args:
            session_id: Session ID this task belongs to
            command: Shell command to execute
            cwd: Working directory (defaults to current directory)
            timeout: Optional timeout in seconds

        Returns:
            Created BackgroundTask
        """
        task_id = str(uuid.uuid4())[:8]
        working_dir = str(cwd) if cwd else str(Path.cwd())

        task = BackgroundTask(
            id=task_id,
            session_id=session_id,
            command=command,
            cwd=working_dir,
        )

        async with self._lock:
            self.tasks[task_id] = task

        # Start execution in background
        task._task = asyncio.create_task(
            self._execute_task(task, timeout)
        )

        await self._broadcast_update(task)
        return task

    async def _execute_task(self, task: BackgroundTask, timeout: float | None = None):
        """Execute the task command."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        await self._broadcast_update(task)

        try:
            # Start subprocess
            process = await asyncio.create_subprocess_shell(
                task.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=task.cwd,
            )
            task._process = process

            # Read output line by line
            async def read_output():
                while True:
                    if process.stdout is None:
                        break
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').rstrip('\n\r')
                    task.output_lines.append(decoded)
                    await self._broadcast_output(task, decoded)

            if timeout:
                try:
                    await asyncio.wait_for(read_output(), timeout=timeout)
                except asyncio.TimeoutError:
                    process.kill()
                    task.error_message = f"Task timed out after {timeout}s"
                    task.status = TaskStatus.FAILED
            else:
                await read_output()

            # Wait for process to complete
            await process.wait()
            task.exit_code = process.returncode

            if task.status != TaskStatus.CANCELLED:
                if task.exit_code == 0:
                    task.status = TaskStatus.COMPLETED
                else:
                    task.status = TaskStatus.FAILED
                    if not task.error_message:
                        task.error_message = f"Command exited with code {task.exit_code}"

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            if task._process:
                try:
                    task._process.kill()
                except ProcessLookupError:
                    pass

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            logger.exception(f"Task {task.id} failed: {e}")

        finally:
            task.completed_at = datetime.now()
            task._process = None
            await self._broadcast_update(task)

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get task by ID."""
        return self.tasks.get(task_id)

    def list_tasks(self, session_id: str | None = None) -> list[BackgroundTask]:
        """List all tasks, optionally filtered by session."""
        tasks = list(self.tasks.values())
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def get_output(
        self,
        task_id: str,
        since_line: int = 0,
        limit: int | None = None,
    ) -> tuple[list[str], bool]:
        """Get task output lines.

        Args:
            task_id: Task ID
            since_line: Start from this line number (0-indexed)
            limit: Maximum number of lines to return

        Returns:
            Tuple of (lines, has_more)
        """
        task = self.tasks.get(task_id)
        if not task:
            return [], False

        lines = task.output_lines[since_line:]
        has_more = False

        if limit and len(lines) > limit:
            lines = lines[:limit]
            has_more = True

        return lines, has_more

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False

        task.status = TaskStatus.CANCELLED

        # Kill process
        if task._process:
            try:
                task._process.kill()
            except ProcessLookupError:
                pass

        # Cancel asyncio task
        if task._task and not task._task.done():
            task._task.cancel()

        await self._broadcast_update(task)
        return True

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task (must be completed/cancelled/failed)."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            await self.cancel_task(task_id)

        async with self._lock:
            del self.tasks[task_id]

        return True

    async def cleanup_session_tasks(self, session_id: str):
        """Cancel and remove all tasks for a session."""
        session_tasks = [t for t in self.tasks.values() if t.session_id == session_id]
        for task in session_tasks:
            await self.cancel_task(task.id)
            async with self._lock:
                if task.id in self.tasks:
                    del self.tasks[task.id]


# Global instance
background_task_manager = BackgroundTaskManager()
