"""Chat session storage - JSON file-based persistence.

Stores chat sessions in .arche/chat/ directory with full state preservation.
Supports save, load, list, and delete operations.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from arche.core import DataModel

logger = logging.getLogger(__name__)


# === Storage DTOs ===
# These are simplified dataclasses for JSON serialization.
# They mirror the core domain models but use string timestamps for JSON compatibility.


@dataclass
class SavedSession(DataModel):
    """Complete serializable session data.

    Uses DataModel base for automatic to_dict() serialization.
    """
    id: str = ""
    name: str = ""
    created_at: str = ""
    updated_at: str = ""

    # Configuration
    model: str = ""
    cwd: str = ""
    permission_mode: str = "default"
    engine: str = "claude_sdk"
    enabled_capabilities: list[str] = field(default_factory=list)

    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0

    # Conversation - stored as raw dicts for simplicity
    messages: list[dict] = field(default_factory=list)
    current_turn: int = 0

    # DeepAgents state - stored as raw dicts
    todos: list[dict] = field(default_factory=list)
    file_operations: list[dict] = field(default_factory=list)
    loaded_skills: list[str] = field(default_factory=list)

    # Extended features
    thinking_mode: str = "normal"
    system_prompt: str | None = None
    budget_usd: float | None = None

    # Resume info
    resume_session_id: str | None = None


@dataclass
class SessionSummary(DataModel):
    """Lightweight session summary for listing."""
    id: str = ""
    name: str = ""
    created_at: str = ""
    updated_at: str = ""
    model: str = ""
    engine: str = "claude_sdk"
    message_count: int = 0
    first_message_preview: str | None = None
    total_cost_usd: float = 0.0

    def to_dict(self) -> dict:
        """Custom to_dict to add is_saved flag."""
        result = super().to_dict()
        result["is_saved"] = True
        return result


class ChatStorage:
    """File-based chat session storage.

    Stores sessions as JSON files in .arche/chat/ directory.
    Each session is stored in a separate file named {session_id}.json.
    """

    def __init__(self, arche_dir: Path):
        """Initialize storage.

        Args:
            arche_dir: Path to .arche directory
        """
        self.storage_dir = arche_dir / "chat"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ChatStorage initialized at {self.storage_dir}")

    def _get_session_path(self, session_id: str) -> Path:
        """Get path to session file."""
        # Sanitize session_id to prevent path traversal
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.storage_dir / f"{safe_id}.json"

    async def save_session(self, session: Any) -> bool:
        """Save a session to storage.

        Args:
            session: Session object from interactive.py

        Returns:
            True if saved successfully
        """
        try:
            # Convert Session to SavedSession using domain models' to_dict()
            saved = SavedSession(
                id=session.id,
                name=session.name,
                created_at=session.created_at.isoformat(),
                updated_at=datetime.now().isoformat(),
                model=session.model,
                cwd=session.cwd,
                permission_mode=session.permission_mode,
                engine=session.engine,
                enabled_capabilities=session.enabled_capabilities,
                input_tokens=session.input_tokens,
                output_tokens=session.output_tokens,
                total_cost_usd=session.total_cost_usd,
                # Use domain models' to_dict() for automatic serialization
                messages=[m.to_dict() for m in session.messages],
                current_turn=session.current_turn,
                todos=[t.to_dict() for t in session.todos],
                file_operations=[f.to_dict() for f in session.file_operations[-100:]],
                loaded_skills=session.loaded_skills,
                thinking_mode=session.thinking_mode,
                system_prompt=session.system_prompt,
                budget_usd=session.budget_usd,
                resume_session_id=session.resume_session_id,
            )

            # Write to file
            session_path = self._get_session_path(session.id)
            with open(session_path, "w") as f:
                json.dump(saved.to_dict(), f, indent=2)

            logger.info(f"Saved session {session.id} to {session_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            return False

    async def load_session(self, session_id: str) -> SavedSession | None:
        """Load a session from storage.

        Args:
            session_id: Session ID to load

        Returns:
            SavedSession if found, None otherwise
        """
        try:
            session_path = self._get_session_path(session_id)
            if not session_path.exists():
                logger.warning(f"Session file not found: {session_path}")
                return None

            with open(session_path) as f:
                data = json.load(f)

            return SavedSession.from_dict(data)

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def list_sessions(self, limit: int = 50) -> list[SessionSummary]:
        """List saved sessions.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session summaries, sorted by updated_at descending
        """
        summaries: list[SessionSummary] = []

        try:
            for session_file in self.storage_dir.glob("*.json"):
                try:
                    with open(session_file) as f:
                        data = json.load(f)

                    # Extract first message preview
                    first_preview = None
                    messages = data.get("messages", [])
                    for msg in messages:
                        if msg.get("role") == "user":
                            content = msg.get("content", [])
                            for block in content:
                                if block.get("type") == "text":
                                    first_preview = str(block.get("content", ""))[:100]
                                    break
                            if first_preview:
                                break

                    summaries.append(SessionSummary(
                        id=data.get("id", session_file.stem),
                        name=data.get("name", ""),
                        created_at=data.get("created_at", ""),
                        updated_at=data.get("updated_at", ""),
                        model=data.get("model", ""),
                        engine=data.get("engine", "claude_sdk"),
                        message_count=len(messages),
                        first_message_preview=first_preview,
                        total_cost_usd=data.get("total_cost_usd", 0.0),
                    ))

                except Exception as e:
                    logger.warning(f"Failed to read session file {session_file}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")

        # Sort by updated_at descending
        summaries.sort(
            key=lambda s: s.updated_at if s.updated_at else "",
            reverse=True
        )

        return summaries[:limit]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a saved session.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            session_path = self._get_session_path(session_id)
            if session_path.exists():
                session_path.unlink()
                logger.info(f"Deleted session {session_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    async def export_session(self, session_id: str, format: str = "json") -> str | None:
        """Export a session to a string format.

        Args:
            session_id: Session ID to export
            format: Export format ('json' or 'markdown')

        Returns:
            Exported string or None if failed
        """
        session = await self.load_session(session_id)
        if not session:
            return None

        if format == "json":
            return json.dumps(session.to_dict(), indent=2)

        elif format == "markdown":
            lines = [
                f"# {session.name}",
                "",
                f"**Session ID:** {session.id}",
                f"**Model:** {session.model}",
                f"**Engine:** {session.engine}",
                f"**Created:** {session.created_at}",
                f"**Last Updated:** {session.updated_at}",
                f"**Total Cost:** ${session.total_cost_usd:.4f}",
                "",
                "---",
                "",
            ]

            for msg in session.messages:
                role_emoji = "👤" if msg.role == "user" else "🤖"
                lines.append(f"## {role_emoji} {msg.role.capitalize()}")
                lines.append("")

                for block in msg.content:
                    block_type = block.get("type", "")
                    content = block.get("content", "")

                    if block_type == "text":
                        lines.append(str(content))
                    elif block_type == "thinking":
                        lines.append("> **Thinking:**")
                        for line in str(content).split("\n"):
                            lines.append(f"> {line}")
                    elif block_type == "tool_use":
                        tool_name = block.get("tool_name", "unknown")
                        lines.append(f"**Tool Use:** `{tool_name}`")
                        lines.append("```json")
                        lines.append(json.dumps(content, indent=2))
                        lines.append("```")
                    elif block_type == "tool_result":
                        lines.append("**Tool Result:**")
                        lines.append("```")
                        lines.append(str(content)[:500])
                        lines.append("```")

                    lines.append("")

                lines.append("---")
                lines.append("")

            return "\n".join(lines)

        return None

    async def import_session(self, data: str, format: str = "json") -> SavedSession | None:
        """Import a session from a string.

        Args:
            data: Session data string
            format: Import format ('json' only for now)

        Returns:
            SavedSession if successful, None otherwise
        """
        if format != "json":
            logger.error(f"Unsupported import format: {format}")
            return None

        try:
            session_data = json.loads(data)
            session = SavedSession.from_dict(session_data)

            # Save to storage
            session_path = self._get_session_path(session.id)
            with open(session_path, "w") as f:
                json.dump(session.to_dict(), f, indent=2)

            logger.info(f"Imported session {session.id}")
            return session

        except Exception as e:
            logger.error(f"Failed to import session: {e}")
            return None
