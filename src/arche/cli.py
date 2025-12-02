#!/usr/bin/env python3
"""Arche - Long-lived coding agent runner."""

import asyncio
import json
import os
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import typer
import yaml
from jinja2 import Template

from arche.engines import create_engine, EventType

app = typer.Typer(
    name="arche",
    help="Long-lived coding agent with exec/review alternation.",
    no_args_is_help=True,
    add_completion=False,
)

# File names
LOG, PID = "arche.log", "arche.pid"
RULE_EXEC, RULE_REVIEW, RULE_RETRO, RULE_COMMON, PROMPT = "RULE_EXEC.md", "RULE_REVIEW.md", "RULE_RETRO.md", "RULE_COMMON.md", "PROMPT.md"
PROJECT_RULES = "PROJECT_RULES.md"
INFINITE, FORCE_REVIEW, FORCE_RETRO, BATCH_MODE, TURN_FILE = "infinite", "force_review", "force_retro", "batch", "turn.txt"
ENGINE_CONFIG, RETRO_EVERY = "engine.json", "retro_every"
PKG_DIR = Path(__file__).parent


def find_arche_dir() -> Path | None:
    """Walk up from cwd to find .arche/ directory."""
    p = Path.cwd().resolve()
    while True:
        if (p / ".arche").is_dir():
            return p / ".arche"
        if p == p.parent:
            return None
        p = p.parent


def get_arche_dir() -> Path:
    """Get .arche/ directory or exit."""
    if d := find_arche_dir():
        return d
    typer.echo("Error: No .arche/ found. Run 'arche start <goal>'.", err=True)
    raise typer.Exit(1)


def is_running(arche_dir: Path) -> tuple[bool, int | None]:
    """Check if Arche is running."""
    pid_file = arche_dir / PID
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return False, None


def kill_arche(pid: int, force: bool = False):
    """Kill Arche process group."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def read_file(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def list_tools(arche_dir: Path) -> str:
    """List tools in .arche/tools/."""
    tools_dir = arche_dir / "tools"
    if not tools_dir.exists():
        return ""
    tools = [f.stem for f in sorted(tools_dir.glob("*.py"))]
    return ", ".join(tools) if tools else ""


def read_latest_journal(arche_dir: Path, journal_path: str | None = None) -> str:
    """Read specific or latest journal."""
    if journal_path:
        # Handle both relative and absolute paths
        full_path = arche_dir / journal_path if not journal_path.startswith("/") else Path(journal_path)
        if full_path.exists():
            return full_path.read_text()
    journals = sorted((arche_dir / "journal").glob("*.yaml"), reverse=True) if (arche_dir / "journal").exists() else []
    return journals[0].read_text() if journals else ""


def read_goal_from_plan(arche_dir: Path) -> str | None:
    """Read goal from latest plan file."""
    plans = sorted((arche_dir / "plan").glob("*.yaml"), reverse=True) if (arche_dir / "plan").exists() else []
    return yaml.safe_load(plans[0].read_text()).get("goal") if plans else None


def parse_reviewer_json(output: str) -> dict | None:
    """Parse JSON from reviewer output."""
    if m := re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL):
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for start in [m.start() for m in re.finditer(r'\{\s*"(?:status|next_task)', output)]:
        depth, end = 0, start
        for i, c in enumerate(output[start:], start):
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            if depth == 0:
                end = i + 1
                break
        try:
            return json.loads(output[start:end])
        except json.JSONDecodeError:
            continue
    return None


def build_system_prompt(arche_dir: Path, mode: str) -> str:
    """Build system prompt from templates. mode: 'exec', 'review', 'retro'"""
    infinite = (arche_dir / INFINITE).exists()
    batch = (arche_dir / BATCH_MODE).exists()
    tools = list_tools(arche_dir)

    common = Template(read_file(arche_dir / RULE_COMMON) or read_file(PKG_DIR / RULE_COMMON)).render(tools=tools)
    rule_map = {"exec": RULE_EXEC, "review": RULE_REVIEW, "retro": RULE_RETRO}
    rule_name = rule_map.get(mode, RULE_EXEC)
    rule_content = read_file(arche_dir / rule_name) or read_file(PKG_DIR / rule_name)

    return Template(rule_content).render(infinite=infinite, batch=batch, common=common)


def build_user_prompt(turn: int, arche_dir: Path, goal: str | None, mode: str,
                      next_task: str | None, journal_file: str | None, resumed: bool) -> str:
    """Build user prompt from template. mode: 'exec', 'review', 'retro'"""
    tpl = Template(read_file(PKG_DIR / PROMPT) or "Turn {{ turn }}.")
    if mode == "retro":
        return f"Turn {turn}. Mode: RETRO.\nGoal: {goal}\n\nConduct retrospective. Review all progress, update PROJECT_RULES.md."
    if mode == "review":
        return tpl.render(turn=turn, goal=goal, review_mode=True,
                         prev_journal=read_latest_journal(arche_dir), resumed=resumed)
    return tpl.render(turn=turn, goal=goal, review_mode=False,
                     next_task=next_task or goal or "Continue with the plan",
                     context_journal=read_latest_journal(arche_dir, journal_file) if journal_file else "")


async def run_loop(arche_dir: Path, goal: str | None = None, engine_type: str = "claude_sdk", engine_kwargs: dict | None = None):
    """Main exec/review/retro loop."""
    project_root = arche_dir.parent
    log_file = arche_dir / LOG
    infinite = (arche_dir / INFINITE).exists()
    retro_config = read_file(arche_dir / RETRO_EVERY) or "off"
    retro_every = int(retro_config) if retro_config.isdigit() else 0  # auto or off = 0 (plan-driven)

    # Restore state
    turn = int(read_file(arche_dir / TURN_FILE) or "1")
    goal = goal or read_goal_from_plan(arche_dir)
    next_task, journal_file = None, None

    # Create engine
    engine_kwargs = engine_kwargs or {}
    engine_kwargs["cwd"] = project_root
    engine = create_engine(engine_type, **engine_kwargs)

    while True:
        # Save current turn
        (arche_dir / TURN_FILE).write_text(str(turn))

        # Determine mode
        resumed = False
        if (arche_dir / FORCE_RETRO).exists():
            (arche_dir / FORCE_RETRO).unlink()
            mode = "retro"
        elif (arche_dir / FORCE_REVIEW).exists():
            (arche_dir / FORCE_REVIEW).unlink()
            mode, resumed = "review", True
        elif retro_every > 0 and turn > 1 and turn % retro_every == 0:
            mode = "retro"
        else:
            mode = "review" if turn % 2 == 0 else "exec"

        # Build prompts
        system_prompt = build_system_prompt(arche_dir, mode)
        user_prompt = build_user_prompt(turn, arche_dir, goal, mode, next_task, journal_file, resumed)

        try:
            with open(log_file, "a") as f:
                f.write(f"\n{'='*50}\nTurn {turn} ({mode.upper()}) - {datetime.now().isoformat()}\n{'='*50}\n")
                f.flush()

                output = ""
                async for event in engine.run(goal=user_prompt, system_prompt=system_prompt):
                    if event.type == EventType.CONTENT and event.content:
                        output += event.content
                        f.write(event.content)
                        f.flush()
                    elif event.type == EventType.TOOL_CALL:
                        f.write(f"[TOOL] {event.tool_name}\n")
                        f.flush()
                    elif event.type == EventType.ERROR:
                        f.write(f"*** Error: {event.error} ***\n")
                        f.flush()

                if mode in ("review", "retro"):
                    if resp := parse_reviewer_json(output):
                        f.write(f"\n*** {mode.upper()}: {resp} ***\n")
                        if not infinite and resp.get("status") == "done":
                            f.write("\n*** Done ***\n")
                            break
                        next_task, journal_file = resp.get("next_task"), resp.get("journal_file")
                    else:
                        f.write(f"\n*** Warning: No {mode} JSON ***\n")
                        next_task, journal_file = None, None

                turn += 1
                await asyncio.sleep(1)

        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"\n*** Error: {e} ***\n")
            await asyncio.sleep(5)


def daemon_main(arche_dir: Path, goal: str | None, engine_type: str, engine_kwargs: dict | None):
    """Daemon entry point."""
    pid_file = arche_dir / PID
    pid_file.write_text(str(os.getpid()))
    try:
        asyncio.run(run_loop(arche_dir, goal, engine_type, engine_kwargs))
    finally:
        pid_file.unlink(missing_ok=True)


def start_daemon(arche_dir: Path, goal: str | None, engine_type: str, engine_kwargs: dict | None):
    """Start daemon process."""
    import subprocess
    import base64

    goal_b64 = base64.b64encode((goal or "").encode()).decode()
    kwargs_b64 = base64.b64encode(json.dumps(engine_kwargs or {}).encode()).decode()

    subprocess.Popen(
        [sys.executable, "-c", f"""
import sys, base64, json; sys.path.insert(0, '{PKG_DIR.parent}')
from arche.cli import daemon_main; from pathlib import Path
g = base64.b64decode('{goal_b64}').decode() or None
k = json.loads(base64.b64decode('{kwargs_b64}').decode())
daemon_main(Path('{arche_dir}'), g, '{engine_type}', k)
"""],
        start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def tail_log(arche_dir: Path):
    """Tail log file."""
    import subprocess
    log_file = arche_dir / LOG
    if not log_file.exists():
        log_file.write_text("")
    try:
        subprocess.run(["tail", "-f", "-n", "100", str(log_file)])
    except KeyboardInterrupt:
        typer.echo("\nDetached. Arche continues in background. Run 'arche stop' to stop.", err=True)


@app.command()
def start(
    goal: str = typer.Argument(..., help="Goal for Arche to achieve"),
    engine: str = typer.Option("claude_sdk", "-e", "--engine", help="Engine: claude_sdk, deepagents, codex"),
    model: str = typer.Option(None, "-m", "--model", help="Model to use"),
    infinite: bool = typer.Option(False, "-i", "--infinite", help="Run infinitely"),
    batch: bool = typer.Option(False, "-b", "--batch", help="Exec all tasks at once"),
    retro_every: str = typer.Option("auto", "-r", "--retro-every", help="Retro schedule: auto, N (every N turns), off"),
    force: bool = typer.Option(False, "-f", "--force", help="Restart if running"),
):
    """Start Arche with specified engine."""
    arche_dir = Path.cwd() / ".arche"

    if arche_dir.exists():
        running, pid = is_running(arche_dir)
        if running and not force:
            typer.echo(f"Already running (PID {pid}). Use -f to restart.", err=True)
            return tail_log(arche_dir)
        if running:
            typer.echo(f"Stopping PID {pid}...")
            kill_arche(pid)
            time.sleep(1)

    arche_dir.mkdir(exist_ok=True)
    (arche_dir / "journal").mkdir(exist_ok=True)
    (arche_dir / "plan").mkdir(exist_ok=True)
    (arche_dir / "retrospective").mkdir(exist_ok=True)

    # Only copy PROJECT_RULES (project-specific state). RULE_* files are read from PKG_DIR with .arche/ override.
    if not (arche_dir / PROJECT_RULES).exists():
        (arche_dir / PROJECT_RULES).write_text(read_file(PKG_DIR / PROJECT_RULES))

    # Engine config
    engine_kwargs = {}
    if model:
        engine_kwargs["model"] = model

    (arche_dir / ENGINE_CONFIG).write_text(json.dumps({"type": engine, "kwargs": engine_kwargs}))
    (arche_dir / TURN_FILE).write_text("1")
    (arche_dir / INFINITE).touch() if infinite else (arche_dir / INFINITE).unlink(missing_ok=True)
    (arche_dir / BATCH_MODE).touch() if batch else (arche_dir / BATCH_MODE).unlink(missing_ok=True)
    if retro_every != "off":
        (arche_dir / RETRO_EVERY).write_text(retro_every)
    else:
        (arche_dir / RETRO_EVERY).unlink(missing_ok=True)
    (arche_dir / LOG).write_text(f"Started: {datetime.now().isoformat()}\nGoal: {goal}\nEngine: {engine}\n")

    typer.echo(f"Goal: {goal}")
    typer.echo(f"Engine: {engine}")
    start_daemon(arche_dir, goal, engine, engine_kwargs)
    time.sleep(0.5)
    tail_log(arche_dir)


@app.command()
def stop():
    """Stop Arche."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)
    if not running:
        typer.echo("Not running.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Stopping PID {pid}...")
    kill_arche(pid)
    for _ in range(10):
        time.sleep(0.5)
        if not is_running(arche_dir)[0]:
            typer.echo("Stopped.")
            return
    kill_arche(pid, force=True)
    (arche_dir / PID).unlink(missing_ok=True)
    typer.echo("Killed.")


@app.command()
def resume():
    """Resume Arche (starts with review mode)."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)
    if running:
        typer.echo(f"Already running (PID {pid}).")
        return tail_log(arche_dir)

    # Load engine config
    config = json.loads(read_file(arche_dir / ENGINE_CONFIG) or '{"type": "claude_sdk", "kwargs": {}}')
    engine_type = config.get("type", "claude_sdk")
    engine_kwargs = config.get("kwargs", {})

    (arche_dir / FORCE_REVIEW).touch()

    with open(arche_dir / LOG, "a") as f:
        f.write(f"\n{'='*50}\nResumed: {datetime.now().isoformat()}\n{'='*50}\n")

    typer.echo("Resuming (review mode)...")
    start_daemon(arche_dir, None, engine_type, engine_kwargs)
    time.sleep(0.5)
    tail_log(arche_dir)


@app.command()
def log(
    follow: bool = typer.Option(True, "-f/--no-follow", help="Follow in real-time"),
    lines: int = typer.Option(100, "-n", "--lines", help="Lines to show"),
    clear: bool = typer.Option(False, "-c", "--clear", help="Clear log"),
):
    """Show logs."""
    arche_dir = get_arche_dir()
    log_file = arche_dir / LOG
    if clear:
        log_file.write_text("")
        return typer.echo("Cleared.")
    if not log_file.exists():
        typer.echo("No log.", err=True)
        raise typer.Exit(1)
    if follow:
        tail_log(arche_dir)
    else:
        typer.echo("\n".join(log_file.read_text().split('\n')[-lines:]))


@app.command()
def status():
    """Show status."""
    if not (arche_dir := find_arche_dir()):
        return typer.echo("No .arche/ found.")

    running, pid = is_running(arche_dir)
    config = json.loads(read_file(arche_dir / ENGINE_CONFIG) or '{"type": "claude_sdk"}')
    mode = ("infinite" if (arche_dir / INFINITE).exists() else "task") + (" batch" if (arche_dir / BATCH_MODE).exists() else "")

    typer.echo(f"Dir: {arche_dir}")
    typer.echo(f"Status: {'Running (PID ' + str(pid) + ')' if running else 'Stopped'}")
    typer.echo(f"Engine: {config.get('type', 'claude_sdk')}")
    typer.echo(f"Mode: {mode}")


@app.command()
def feedback(
    message: str = typer.Argument(..., help="Feedback message"),
    priority: str = typer.Option("medium", "-p", help="high/medium/low"),
    now: bool = typer.Option(False, "-n", "--now", help="Interrupt and review now"),
):
    """Add feedback."""
    arche_dir = get_arche_dir()
    pending = arche_dir / "feedback" / "pending"
    pending.mkdir(parents=True, exist_ok=True)

    ts = datetime.now()
    slug = re.sub(r'[^a-z0-9-]', '-', message[:30].lower())
    (pending / f"{ts:%Y%m%d-%H%M}-{slug}.yaml").write_text(
        f'meta:\n  timestamp: "{ts.isoformat()}"\nsummary: "{message}"\npriority: "{priority}"\nstatus: "pending"\n'
    )
    typer.echo("Feedback added.")

    if now:
        (arche_dir / FORCE_REVIEW).touch()
        running, pid = is_running(arche_dir)
        if running:
            typer.echo(f"Interrupting PID {pid}...")
            kill_arche(pid)
            time.sleep(1)

        config = json.loads(read_file(arche_dir / ENGINE_CONFIG) or '{"type": "claude_sdk", "kwargs": {}}')
        typer.echo("Starting review...")
        start_daemon(arche_dir, None, config.get("type", "claude_sdk"), config.get("kwargs", {}))
        time.sleep(0.5)
        tail_log(arche_dir)


@app.command()
def retro():
    """Trigger retrospective mode."""
    arche_dir = get_arche_dir()
    (arche_dir / FORCE_RETRO).touch()

    running, pid = is_running(arche_dir)
    if running:
        typer.echo(f"Interrupting PID {pid} for retro...")
        kill_arche(pid)
        time.sleep(1)

    config = json.loads(read_file(arche_dir / ENGINE_CONFIG) or '{"type": "claude_sdk", "kwargs": {}}')
    typer.echo("Starting retrospective...")
    start_daemon(arche_dir, None, config.get("type", "claude_sdk"), config.get("kwargs", {}))
    time.sleep(0.5)
    tail_log(arche_dir)


@app.command()
def version():
    """Show version."""
    from arche import __version__
    typer.echo(f"arche {__version__}")


if __name__ == "__main__":
    app()
