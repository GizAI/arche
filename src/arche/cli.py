#!/usr/bin/env python3
"""Arche - Long-lived coding agent runner for Claude Code."""

import os
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import typer
from jinja2 import Template

app = typer.Typer(
    name="arche",
    help="Long-lived coding agent that runs Claude Code.",
    no_args_is_help=True,
    add_completion=False,
)

LOG_FILE = "arche.log"
PID_FILE = "arche.pid"
RULE_FILE = "RULE.md"
PROMPT_FILE = "PROMPT.md"
INFINITE_FLAG = "infinite"
CLAUDE_ARGS_FILE = "claude_args.json"

# Package directory (where RULE.md lives)
PKG_DIR = Path(__file__).parent


def get_rule_content() -> str:
    """Read RULE.md from package."""
    rule_file = PKG_DIR / RULE_FILE
    if rule_file.exists():
        return rule_file.read_text()
    return ""


def get_prompt_template() -> str:
    """Read PROMPT.md template from package."""
    prompt_file = PKG_DIR / PROMPT_FILE
    if prompt_file.exists():
        return prompt_file.read_text()
    return "Turn {{ turn }}. Goal: {{ goal }}."


def find_arche_dir() -> Path | None:
    """Walk up from cwd to find .arche/ directory."""
    current = Path.cwd().resolve()
    while current != current.parent:
        arche_dir = current / ".arche"
        if arche_dir.is_dir():
            return arche_dir
        current = current.parent
    arche_dir = current / ".arche"
    if arche_dir.is_dir():
        return arche_dir
    return None


def get_arche_dir() -> Path:
    """Get .arche/ directory or exit with error."""
    arche_dir = find_arche_dir()
    if arche_dir is None:
        typer.echo("Error: No .arche/ directory found.", err=True)
        typer.echo("Run 'arche start <goal>' to create one.", err=True)
        raise typer.Exit(1)
    return arche_dir


def get_pid_file(arche_dir: Path) -> Path:
    return arche_dir / PID_FILE


def get_log_file(arche_dir: Path) -> Path:
    return arche_dir / LOG_FILE


def is_infinite(arche_dir: Path) -> bool:
    """Check if infinite mode (flag file exists)."""
    return (arche_dir / INFINITE_FLAG).exists()


def set_infinite(arche_dir: Path, infinite: bool):
    """Set or unset infinite mode flag."""
    flag_file = arche_dir / INFINITE_FLAG
    if infinite:
        flag_file.touch()
    else:
        flag_file.unlink(missing_ok=True)


def save_claude_args(arche_dir: Path, args: list[str]):
    """Save extra claude args to JSON file."""
    import json
    args_file = arche_dir / CLAUDE_ARGS_FILE
    if args:
        args_file.write_text(json.dumps(args))
    else:
        args_file.unlink(missing_ok=True)


def load_claude_args(arche_dir: Path) -> list[str]:
    """Load extra claude args from JSON file."""
    import json
    args_file = arche_dir / CLAUDE_ARGS_FILE
    if args_file.exists():
        return json.loads(args_file.read_text())
    return []


def is_running(arche_dir: Path) -> tuple[bool, Optional[int]]:
    """Check if Arche is running. Returns (is_running, pid)."""
    pid_file = get_pid_file(arche_dir)
    if not pid_file.exists():
        return False, None

    try:
        pid = int(pid_file.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        # Clean up stale pid file
        pid_file.unlink(missing_ok=True)
        return False, None


def ensure_claude_available() -> None:
    if shutil.which("claude") is None:
        typer.echo("Error: `claude` CLI not found in PATH.", err=True)
        raise typer.Exit(1)


def build_claude_cmd(
    turn: int,
    arche_dir: Path,
    goal: str | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build the claude CLI command for a single turn."""

    rule_file = arche_dir / RULE_FILE
    infinite = is_infinite(arche_dir)

    cmd: list[str] = [
        "claude", "--print",
        "--permission-mode", "plan",
    ]

    # Render system prompt from RULE.md template
    if rule_file.exists():
        rule_template = Template(rule_file.read_text())
        rule_prompt = rule_template.render(infinite=infinite)
        cmd.extend(["--system-prompt", rule_prompt])

    # Add extra claude args (passed through from arche start)
    if extra_args:
        cmd.extend(extra_args)

    # Render prompt from PROMPT.md template
    prompt_template = Template(get_prompt_template())
    prompt = prompt_template.render(turn=turn, goal=goal or "Continue", infinite=infinite)
    cmd.append(prompt)
    return cmd


def run_arche_loop(arche_dir: Path, goal: str | None = None, extra_args: list[str] | None = None):
    """Main Arche loop - runs Claude in turns until ARCHE_DONE."""
    log_file = get_log_file(arche_dir)
    infinite = is_infinite(arche_dir)
    turn = 1

    while True:
        # Pass goal only on first turn
        cmd = build_claude_cmd(turn, arche_dir, goal if turn == 1 else None, extra_args)

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"Turn {turn} - {datetime.now().isoformat()}\n")
                f.write(f"{'='*50}\n")
                f.flush()

                proc = subprocess.Popen(
                    cmd,
                    cwd=str(arche_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )

                full_output = ""
                while True:
                    chunk = proc.stdout.read(1)
                    if not chunk:
                        break
                    decoded = chunk.decode('utf-8', errors='replace')
                    full_output += decoded
                    f.write(decoded)
                    f.flush()

                proc.wait()

                if "ARCHE_DONE" in full_output and not infinite:
                    f.write(f"\n\n*** ARCHE_DONE - Stopping ***\n")
                    break
                elif "ARCHE_DONE" in full_output and infinite:
                    f.write(f"\n\n*** ARCHE_DONE - Infinite mode, continuing... ***\n")

                if proc.returncode != 0:
                    f.write(f"\n\n*** Turn {turn} failed (code {proc.returncode}) ***\n")
                    time.sleep(5)

                turn += 1
                time.sleep(1)

        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"\n\n*** Error: {e} ***\n")
            time.sleep(5)


def daemon_main(arche_dir: Path, goal: str | None = None, extra_args: list[str] | None = None):
    """Entry point for daemon process."""
    pid_file = get_pid_file(arche_dir)

    # Write PID
    pid_file.write_text(str(os.getpid()))

    try:
        run_arche_loop(arche_dir, goal, extra_args)
    finally:
        pid_file.unlink(missing_ok=True)


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def start(
    ctx: typer.Context,
    goal: str = typer.Argument(..., help="The main goal for Arche to achieve"),
    infinite: bool = typer.Option(False, "--infinite", "-i", help="Run infinitely, keep finding next goals"),
    force: bool = typer.Option(False, "--force", "-f", help="Restart if already running"),
):
    """Start Arche with a goal. Creates .arche/ if needed.

    Extra arguments after -- are passed to claude CLI.
    Example: arche start "goal" -- --model opus --add-dir ../other
    """
    ensure_claude_available()

    arche_dir = Path.cwd() / ".arche"
    is_new = not arche_dir.exists()
    extra_args = ctx.args  # Capture extra args for claude

    # Check if already running
    if arche_dir.exists():
        running, pid = is_running(arche_dir)
        if running and not force:
            typer.echo(f"Arche already running (PID {pid}). Use --force to restart.", err=True)
            typer.echo("Tailing log...", err=True)
            tail_log(arche_dir)
            return
        elif running and force:
            typer.echo(f"Stopping existing Arche (PID {pid})...", err=True)
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)

    # Create directory structure
    arche_dir.mkdir(exist_ok=True)

    # Copy RULE.md from package
    rule_dest = arche_dir / RULE_FILE
    if not rule_dest.exists() or force:
        rule_dest.write_text(get_rule_content())

    # Set infinite mode flag
    set_infinite(arche_dir, infinite)

    # Save extra claude args for resume
    save_claude_args(arche_dir, extra_args)

    # Clear old log
    log_file = get_log_file(arche_dir)
    log_file.write_text(f"Arche started: {datetime.now().isoformat()}\nGoal: {goal}\n\n")

    if is_new:
        typer.echo(f"Created .arche/ at {arche_dir}")
    typer.echo(f"Goal: {goal}")
    if extra_args:
        typer.echo(f"Claude args: {' '.join(extra_args)}")
    typer.echo("Starting Arche in background...")

    # Start daemon process (pass goal and args via base64 to avoid escaping issues)
    import base64
    import json
    goal_b64 = base64.b64encode(goal.encode()).decode()
    args_b64 = base64.b64encode(json.dumps(extra_args).encode()).decode()
    proc = subprocess.Popen(
        [sys.executable, "-c", f"""
import sys, base64, json
sys.path.insert(0, '{Path(__file__).parent.parent}')
from arche.cli import daemon_main
from pathlib import Path
goal = base64.b64decode('{goal_b64}').decode()
extra_args = json.loads(base64.b64decode('{args_b64}').decode())
daemon_main(Path('{arche_dir}'), goal, extra_args)
"""],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(0.5)
    typer.echo(f"Arche running (PID {proc.pid}). Ctrl+C to detach from log.")
    tail_log(arche_dir)


@app.command()
def stop():
    """Stop running Arche."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)

    if not running:
        typer.echo("Arche is not running.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Stopping Arche (PID {pid})...")

    # Kill process group to include child processes (claude)
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass

    # Wait for process to end
    for _ in range(10):
        time.sleep(0.5)
        running, _ = is_running(arche_dir)
        if not running:
            typer.echo("Arche stopped.")
            return

    # Force kill
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass

    get_pid_file(arche_dir).unlink(missing_ok=True)
    typer.echo("Arche killed.")


@app.command()
def resume():
    """Resume Arche (restart if stopped)."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)

    if running:
        typer.echo(f"Arche already running (PID {pid}). Tailing log...")
        tail_log(arche_dir)
        return

    # Load saved claude args
    extra_args = load_claude_args(arche_dir)

    typer.echo("Resuming Arche...")
    if extra_args:
        typer.echo(f"Claude args: {' '.join(extra_args)}")

    # Append to log
    log_file = get_log_file(arche_dir)
    with open(log_file, "a") as f:
        f.write(f"\n\n{'='*50}\nResumed: {datetime.now().isoformat()}\n{'='*50}\n\n")

    # Start daemon (no goal - Arche reads from its own plan files)
    import base64
    import json
    args_b64 = base64.b64encode(json.dumps(extra_args).encode()).decode()
    proc = subprocess.Popen(
        [sys.executable, "-c", f"""
import sys, base64, json
sys.path.insert(0, '{Path(__file__).parent.parent}')
from arche.cli import daemon_main
from pathlib import Path
extra_args = json.loads(base64.b64decode('{args_b64}').decode())
daemon_main(Path('{arche_dir}'), None, extra_args)
"""],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(0.5)
    typer.echo(f"Arche running (PID {proc.pid}). Ctrl+C to detach from log.")
    tail_log(arche_dir)


def tail_log(arche_dir: Path):
    """Tail the log file."""
    log_file = get_log_file(arche_dir)
    if not log_file.exists():
        log_file.write_text("")

    try:
        subprocess.run(["tail", "-f", "-n", "100", str(log_file)])
    except KeyboardInterrupt:
        typer.echo("\nDetached from log. Arche continues in background.", err=True)


@app.command()
def log(
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f", help="Follow log in real-time"),
    lines: int = typer.Option(100, "--lines", "-n", help="Number of lines to show"),
    clear: bool = typer.Option(False, "--clear", "-c", help="Clear log file"),
):
    """Show Arche logs."""
    arche_dir = get_arche_dir()
    log_file = get_log_file(arche_dir)

    if clear:
        log_file.write_text("")
        typer.echo("Log cleared.")
        return

    if not log_file.exists():
        typer.echo("No log file yet.", err=True)
        raise typer.Exit(1)

    if follow:
        tail_log(arche_dir)
    else:
        content = log_file.read_text()
        for line in content.split('\n')[-lines:]:
            typer.echo(line)


@app.command()
def status():
    """Show Arche status."""
    arche_dir = find_arche_dir()

    if not arche_dir:
        typer.echo("No .arche/ found.")
        return

    typer.echo(f"Arche dir: {arche_dir}")
    typer.echo(f"Project root: {arche_dir.parent}")

    running, pid = is_running(arche_dir)
    if running:
        typer.echo(f"Status: Running (PID {pid})")
    else:
        typer.echo("Status: Stopped")

    typer.echo(f"Mode: {'infinite' if is_infinite(arche_dir) else 'task'}")


@app.command()
def feedback(
    message: str = typer.Argument(..., help="Feedback message"),
    priority: str = typer.Option("medium", "--priority", "-p", help="high, medium, low"),
):
    """Add feedback for Arche to process."""
    arche_dir = get_arche_dir()
    pending_dir = arche_dir / "feedback" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    ts = now.strftime("%Y%m%d-%H%M")
    slug = message[:30].lower().replace(" ", "-").replace("/", "-")

    content = f"""meta:
  timestamp: "{now.isoformat()}"
  kind: feedback
  id: "{ts}-feedback"
summary: "{message}"
priority: "{priority}"
status: "pending"
"""

    filepath = pending_dir / f"{ts}-{slug}.yaml"
    filepath.write_text(content)
    typer.echo(f"Feedback added: {filepath.name}")


@app.command()
def version():
    """Show version."""
    from arche import __version__
    typer.echo(f"arche {__version__}")


if __name__ == "__main__":
    app()
