"""Checkpoint system for saving and restoring code state.

Uses git stash for code state management, allowing users to create
snapshots and restore to previous states.
Uses centralized EventBus for broadcasting updates.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable
import json
import logging

from arche.core import event_bus

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """A checkpoint representing a saved code state."""
    id: str
    session_id: str
    name: str
    description: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    stash_ref: str | None = None  # Git stash reference
    file_count: int = 0
    is_dirty: bool = False  # Whether working directory had changes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "stash_ref": self.stash_ref,
            "file_count": self.file_count,
            "is_dirty": self.is_dirty,
        }


# Legacy type alias for backward compatibility
BroadcastCallback = Callable[[str, dict], Awaitable[None]]


class CheckpointManager:
    """Manages checkpoints using git stash.

    Uses centralized EventBus for all broadcasts.
    """

    def __init__(self, working_dir: Path | None = None):
        self.working_dir = working_dir or Path.cwd()
        self.checkpoints: dict[str, Checkpoint] = {}
        self._lock = asyncio.Lock()
        self._checkpoint_file = self.working_dir / ".arche" / "checkpoints.json"

    def set_broadcast_callback(self, callback: BroadcastCallback):
        """Legacy method - broadcasts now go through event_bus."""
        pass

    async def _broadcast_update(self, session_id: str, event_type: str, checkpoint: Checkpoint):
        """Broadcast checkpoint update to session via EventBus."""
        await event_bus.broadcast(session_id, {
            "type": event_type,
            "checkpoint": checkpoint.to_dict(),
        })

    async def _run_git(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        """Run a git command and return (exit_code, stdout, stderr)."""
        work_dir = cwd or self.working_dir
        process = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        stdout, stderr = await process.communicate()
        return (
            process.returncode or 0,
            stdout.decode('utf-8', errors='replace').strip(),
            stderr.decode('utf-8', errors='replace').strip(),
        )

    async def _is_git_repo(self, cwd: Path | None = None) -> bool:
        """Check if directory is a git repository."""
        code, _, _ = await self._run_git("rev-parse", "--git-dir", cwd=cwd)
        return code == 0

    async def _has_changes(self, cwd: Path | None = None) -> tuple[bool, int]:
        """Check if working directory has uncommitted changes.

        Returns: (has_changes, file_count)
        """
        code, stdout, _ = await self._run_git("status", "--porcelain", cwd=cwd)
        if code != 0:
            return False, 0

        lines = [l for l in stdout.split('\n') if l.strip()]
        return len(lines) > 0, len(lines)

    async def create_checkpoint(
        self,
        session_id: str,
        name: str,
        description: str | None = None,
        cwd: Path | None = None,
    ) -> Checkpoint | None:
        """Create a new checkpoint.

        Creates a git stash to save current state, then immediately
        re-applies it to keep the working state intact.

        Args:
            session_id: Session ID
            name: Checkpoint name
            description: Optional description
            cwd: Working directory (defaults to manager's working_dir)

        Returns:
            Created checkpoint or None if failed
        """
        work_dir = cwd or self.working_dir

        if not await self._is_git_repo(work_dir):
            logger.warning(f"Not a git repository: {work_dir}")
            return None

        has_changes, file_count = await self._has_changes(work_dir)

        checkpoint_id = str(uuid.uuid4())[:8]
        stash_message = f"arche-checkpoint-{checkpoint_id}: {name}"

        checkpoint = Checkpoint(
            id=checkpoint_id,
            session_id=session_id,
            name=name,
            description=description,
            file_count=file_count,
            is_dirty=has_changes,
        )

        if has_changes:
            # Create stash with message
            code, stdout, stderr = await self._run_git(
                "stash", "push", "-m", stash_message, "--include-untracked",
                cwd=work_dir,
            )

            if code != 0:
                logger.error(f"Failed to create stash: {stderr}")
                return None

            # Get stash reference
            code, stdout, _ = await self._run_git("stash", "list", cwd=work_dir)
            if code == 0 and stdout:
                # Find our stash
                for line in stdout.split('\n'):
                    if stash_message in line:
                        # Format: stash@{0}: On branch: message
                        checkpoint.stash_ref = line.split(':')[0].strip()
                        break

            # Re-apply stash to keep working state
            code, _, stderr = await self._run_git("stash", "pop", cwd=work_dir)
            if code != 0:
                logger.warning(f"Failed to re-apply stash: {stderr}")
        else:
            # No changes - just record current HEAD
            code, stdout, _ = await self._run_git("rev-parse", "HEAD", cwd=work_dir)
            if code == 0:
                checkpoint.stash_ref = f"commit:{stdout[:8]}"

        async with self._lock:
            self.checkpoints[checkpoint_id] = checkpoint
            await self._save_checkpoints()

        await self._broadcast_update(session_id, "checkpoint_created", checkpoint)
        return checkpoint

    async def restore_checkpoint(
        self,
        session_id: str,
        checkpoint_id: str,
        cwd: Path | None = None,
    ) -> bool:
        """Restore to a checkpoint.

        WARNING: This will discard current uncommitted changes.

        Args:
            session_id: Session ID
            checkpoint_id: Checkpoint to restore
            cwd: Working directory

        Returns:
            True if successful
        """
        checkpoint = self.checkpoints.get(checkpoint_id)
        if not checkpoint:
            return False

        work_dir = cwd or self.working_dir

        if not checkpoint.stash_ref:
            logger.warning(f"Checkpoint {checkpoint_id} has no stash reference")
            return False

        if checkpoint.stash_ref.startswith("commit:"):
            # Restore to specific commit
            commit_hash = checkpoint.stash_ref.split(':')[1]
            code, _, stderr = await self._run_git(
                "checkout", commit_hash, "--", ".",
                cwd=work_dir,
            )
            if code != 0:
                logger.error(f"Failed to restore to commit: {stderr}")
                return False
        else:
            # Stash reference - apply it
            # First, stash current changes if any
            has_changes, _ = await self._has_changes(work_dir)
            if has_changes:
                await self._run_git("stash", "push", "-m", "arche-auto-stash-before-restore", cwd=work_dir)

            # Apply the checkpoint stash
            code, _, stderr = await self._run_git(
                "stash", "apply", checkpoint.stash_ref,
                cwd=work_dir,
            )
            if code != 0:
                logger.error(f"Failed to apply stash: {stderr}")
                # Try to restore the auto-stash
                await self._run_git("stash", "pop", cwd=work_dir)
                return False

        await self._broadcast_update(session_id, "checkpoint_restored", checkpoint)
        return True

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Get checkpoint by ID."""
        return self.checkpoints.get(checkpoint_id)

    def list_checkpoints(self, session_id: str | None = None) -> list[Checkpoint]:
        """List all checkpoints, optionally filtered by session."""
        checkpoints = list(self.checkpoints.values())
        if session_id:
            checkpoints = [c for c in checkpoints if c.session_id == session_id]
        return sorted(checkpoints, key=lambda c: c.created_at, reverse=True)

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        checkpoint = self.checkpoints.get(checkpoint_id)
        if not checkpoint:
            return False

        # Note: We don't delete the git stash as it might have been popped
        # or the user might want to manually access it

        async with self._lock:
            del self.checkpoints[checkpoint_id]
            await self._save_checkpoints()

        return True

    async def _save_checkpoints(self):
        """Save checkpoints to file."""
        self._checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            cp_id: cp.to_dict()
            for cp_id, cp in self.checkpoints.items()
        }
        with open(self._checkpoint_file, 'w') as f:
            json.dump(data, f, indent=2)

    async def load_checkpoints(self):
        """Load checkpoints from file."""
        if not self._checkpoint_file.exists():
            return

        try:
            with open(self._checkpoint_file, 'r') as f:
                data = json.load(f)

            for cp_id, cp_data in data.items():
                self.checkpoints[cp_id] = Checkpoint(
                    id=cp_data["id"],
                    session_id=cp_data["session_id"],
                    name=cp_data["name"],
                    description=cp_data.get("description"),
                    created_at=datetime.fromisoformat(cp_data["created_at"]),
                    stash_ref=cp_data.get("stash_ref"),
                    file_count=cp_data.get("file_count", 0),
                    is_dirty=cp_data.get("is_dirty", False),
                )
        except Exception as e:
            logger.warning(f"Failed to load checkpoints: {e}")


# Global instance
checkpoint_manager = CheckpointManager()
