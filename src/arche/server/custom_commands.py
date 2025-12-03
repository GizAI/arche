"""Custom slash commands loader.

Loads and manages custom commands from .claude/commands/ directory.
Commands are markdown files that define prompts.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class CustomCommand:
    """A custom slash command loaded from a markdown file."""
    name: str
    description: str
    prompt: str
    file_path: Path
    arguments: list[str] = field(default_factory=list)  # Argument placeholders
    loaded_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "prompt": self.prompt[:200] + "..." if len(self.prompt) > 200 else self.prompt,
            "file_path": str(self.file_path),
            "arguments": self.arguments,
            "loaded_at": self.loaded_at.isoformat(),
        }


class CommandManager:
    """Manages custom slash commands."""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self.commands: dict[str, CustomCommand] = {}
        self._built_in_commands = {
            "clear": "Clear conversation history",
            "compact": "Compact conversation to reduce context size",
            "help": "Show available commands",
            "plan": "Enter plan mode (read-only exploration)",
            "model": "Switch to a different model",
            "think": "Set thinking mode (normal, think, think_hard, ultrathink)",
            "checkpoint": "Create a checkpoint of current state",
            "background": "Run a command in the background",
            "mcp": "Manage MCP servers",
            "hooks": "Configure hooks",
        }

    def _get_commands_dir(self, project_dir: Path | None = None) -> Path:
        """Get the commands directory path."""
        base = project_dir or self.project_dir
        return base / ".claude" / "commands"

    def load_commands(self, project_dir: Path | None = None) -> int:
        """Load custom commands from .claude/commands/ directory.

        Commands are markdown files where:
        - Filename (without .md) becomes the command name
        - First line starting with # is the description
        - Rest of the file is the prompt template

        Arguments can be specified with $ARGNAME or {{argname}} placeholders.

        Args:
            project_dir: Project directory to load from

        Returns:
            Number of commands loaded
        """
        commands_dir = self._get_commands_dir(project_dir)

        if not commands_dir.exists():
            logger.debug(f"Commands directory not found: {commands_dir}")
            return 0

        loaded = 0
        for md_file in commands_dir.glob("*.md"):
            try:
                command = self._load_command_file(md_file)
                if command:
                    self.commands[command.name] = command
                    loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load command from {md_file}: {e}")

        logger.info(f"Loaded {loaded} custom commands from {commands_dir}")
        return loaded

    def _load_command_file(self, file_path: Path) -> CustomCommand | None:
        """Load a single command from a markdown file."""
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        if not lines:
            return None

        # Command name from filename (without .md)
        name = file_path.stem

        # Find description (first # heading)
        description = ""
        prompt_start = 0
        for i, line in enumerate(lines):
            if line.startswith('# '):
                description = line[2:].strip()
                prompt_start = i + 1
                break

        # Rest is the prompt template
        prompt = '\n'.join(lines[prompt_start:]).strip()

        if not prompt:
            return None

        # Extract argument placeholders
        arguments = self._extract_arguments(prompt)

        return CustomCommand(
            name=name,
            description=description or f"Custom command: {name}",
            prompt=prompt,
            file_path=file_path,
            arguments=arguments,
        )

    def _extract_arguments(self, prompt: str) -> list[str]:
        """Extract argument placeholders from prompt template."""
        arguments = []

        # Match $ARGNAME style
        for match in re.finditer(r'\$([A-Z_][A-Z0-9_]*)', prompt):
            arg = match.group(1)
            if arg not in arguments:
                arguments.append(arg)

        # Match {{argname}} style
        for match in re.finditer(r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}', prompt):
            arg = match.group(1).upper()
            if arg not in arguments:
                arguments.append(arg)

        return arguments

    def get_command(self, name: str) -> CustomCommand | None:
        """Get a command by name."""
        return self.commands.get(name)

    def list_commands(self) -> list[dict]:
        """List all commands (built-in + custom)."""
        result = []

        # Built-in commands
        for name, desc in self._built_in_commands.items():
            result.append({
                "name": name,
                "description": desc,
                "type": "builtin",
            })

        # Custom commands
        for cmd in self.commands.values():
            result.append({
                "name": cmd.name,
                "description": cmd.description,
                "type": "custom",
                "arguments": cmd.arguments,
            })

        return sorted(result, key=lambda x: x["name"])

    def execute_command(
        self,
        name: str,
        args: list[str] | None = None,
        kwargs: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Execute a command and return the expanded prompt.

        Args:
            name: Command name
            args: Positional arguments
            kwargs: Named arguments

        Returns:
            Tuple of (expanded_prompt, metadata)
        """
        command = self.commands.get(name)
        if not command:
            # Check if it's a built-in command
            if name in self._built_in_commands:
                return "", {"type": "builtin", "name": name}
            raise ValueError(f"Unknown command: {name}")

        prompt = command.prompt
        args = args or []
        kwargs = kwargs or {}

        # Replace positional arguments
        for i, arg_name in enumerate(command.arguments):
            placeholder1 = f"${arg_name}"
            placeholder2 = f"{{{{{arg_name.lower()}}}}}"

            value = ""
            if i < len(args):
                value = args[i]
            elif arg_name in kwargs:
                value = kwargs[arg_name]
            elif arg_name.lower() in kwargs:
                value = kwargs[arg_name.lower()]

            prompt = prompt.replace(placeholder1, value)
            prompt = prompt.replace(placeholder2, value)

        return prompt, {
            "type": "custom",
            "name": name,
            "file_path": str(command.file_path),
        }

    def parse_command_input(self, input_text: str) -> tuple[str, list[str]] | None:
        """Parse command input to extract command name and arguments.

        Supports formats:
        - /command
        - /command arg1 arg2
        - /command "arg with spaces" arg2

        Args:
            input_text: Raw input text

        Returns:
            Tuple of (command_name, args) or None if not a command
        """
        text = input_text.strip()
        if not text.startswith('/'):
            return None

        # Remove leading slash
        text = text[1:]

        # Split into parts, respecting quotes
        parts = []
        current = ""
        in_quotes = False
        quote_char = None

        for char in text:
            if char in '"\'':
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                else:
                    current += char
            elif char == ' ' and not in_quotes:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char

        if current:
            parts.append(current)

        if not parts:
            return None

        command_name = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        return command_name, args

    def reload_commands(self, project_dir: Path | None = None):
        """Reload all commands from disk."""
        self.commands.clear()
        self.load_commands(project_dir)


# Global instance
command_manager = CommandManager()
