#!/usr/bin/env python3
"""Arche - Long-lived coding agent runner."""

import asyncio
import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import typer
import yaml
from jinja2 import Template

from arche.engines import create_engine, EventType

app = typer.Typer(name="arche", help="Long-lived coding agent.", no_args_is_help=True, add_completion=False)

# Constants
LOG, PID, STATE, PROJECT_RULES = "arche.log", "arche.pid", "state.json", "PROJECT_RULES.md"
RULE_EXEC, RULE_REVIEW, RULE_RETRO, RULE_COMMON = "RULE_EXEC.md", "RULE_REVIEW.md", "RULE_RETRO.md", "RULE_COMMON.md"
PROMPT = "PROMPT.md"
INFINITE, FORCE_REVIEW, FORCE_RETRO, STEP_MODE = "infinite", "force_review", "force_retro", "step"
PKG_DIR = Path(__file__).parent
DIRS = ["journal", "plan", "feedback", "feedback/archive", "retrospective", "tools"]

# Tool arg display keys
TOOL_ARG_KEYS = {
    "Read": "file_path", "Write": "file_path", "Edit": "file_path",
    "Bash": "command", "Grep": "pattern", "Glob": "pattern", "Task": "description",
}


# === Utilities ===

def read_file(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def read_state(arche_dir: Path) -> dict:
    try:
        return json.loads((arche_dir / STATE).read_text()) if (arche_dir / STATE).exists() else {}
    except json.JSONDecodeError:
        return {}


def write_state(arche_dir: Path, state: dict):
    (arche_dir / STATE).write_text(json.dumps(state, indent=2))


def find_arche_dir() -> Path | None:
    p = Path.cwd().resolve()
    while p != p.parent:
        if (p / ".arche").is_dir():
            return p / ".arche"
        p = p.parent
    return None


def get_arche_dir() -> Path:
    if d := find_arche_dir():
        return d
    typer.echo("Error: No .arche/ found. Run 'arche start <goal>'.", err=True)
    raise typer.Exit(1)


def is_running(arche_dir: Path) -> tuple[bool, int | None]:
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


def kill_process(pid: int, force: bool = False):
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def stop_and_wait(arche_dir: Path, pid: int) -> bool:
    """Stop process and wait. Returns True if stopped gracefully."""
    typer.echo(f"Stopping PID {pid}...")
    kill_process(pid)
    for _ in range(10):
        time.sleep(0.5)
        if not is_running(arche_dir)[0]:
            return True
    kill_process(pid, force=True)
    (arche_dir / PID).unlink(missing_ok=True)
    return False


def add_feedback(arche_dir: Path, msg: str, priority: str = "medium"):
    """Add feedback file."""
    feedback_dir = arche_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now()
    slug = re.sub(r'[^a-z0-9-]', '-', msg[:30].lower())
    (feedback_dir / f"{ts:%Y%m%d-%H%M}-{slug}.yaml").write_text(
        f'meta:\n  timestamp: "{ts.isoformat()}"\nsummary: "{msg}"\npriority: "{priority}"\n'
    )


def init_arche_dir(arche_dir: Path):
    """Initialize .arche/ directory structure."""
    arche_dir.mkdir(exist_ok=True)
    for d in DIRS:
        (arche_dir / d).mkdir(exist_ok=True)
    if not (arche_dir / PROJECT_RULES).exists():
        (arche_dir / PROJECT_RULES).write_text(read_file(PKG_DIR / PROJECT_RULES))


def reset_arche_dir(arche_dir: Path):
    """Reset .arche/ preserving PROJECT_RULES.md."""
    rules = read_file(arche_dir / PROJECT_RULES)
    shutil.rmtree(arche_dir)
    arche_dir.mkdir()
    if rules:
        (arche_dir / PROJECT_RULES).write_text(rules)


def start_daemon(arche_dir: Path, goal: str | None = None):
    goal_b64 = base64.b64encode((goal or "").encode()).decode()
    subprocess.Popen(
        [sys.executable, "-m", "arche.cli", "daemon", str(arche_dir), goal_b64],
        start_new_session=True, stdout=subprocess.DEVNULL,
        stderr=open(arche_dir / "daemon.err", "a"),
    )


def tail_log(arche_dir: Path):
    log_file = arche_dir / LOG
    if not log_file.exists():
        log_file.write_text("")
    try:
        subprocess.run(["tail", "-f", "-n", "100", str(log_file)])
    except KeyboardInterrupt:
        if is_running(arche_dir)[0]:
            typer.echo("\nDetached. Run 'arche stop' to stop.", err=True)
        else:
            typer.echo("\nArche has finished.", err=True)


# === Prompt Building ===

def list_tools(arche_dir: Path) -> str:
    tools_dir = arche_dir / "tools"
    if not tools_dir.exists():
        return ""
    return ", ".join(f.stem for f in sorted(tools_dir.glob("*.py")))


def read_latest_journal(arche_dir: Path, path: str | None = None) -> str:
    if path:
        full = arche_dir / path if not path.startswith("/") else Path(path)
        if full.exists():
            return full.read_text()
    journal_dir = arche_dir / "journal"
    if journal_dir.exists():
        journals = sorted(journal_dir.glob("*.yaml"), reverse=True)
        if journals:
            return journals[0].read_text()
    return ""


def read_goal_from_plan(arche_dir: Path) -> str | None:
    plan_dir = arche_dir / "plan"
    if plan_dir.exists():
        plans = sorted(plan_dir.glob("*.yaml"), reverse=True)
        if plans:
            return yaml.safe_load(plans[0].read_text()).get("goal")
    return None


def read_feedback(arche_dir: Path) -> str:
    """Read all pending feedback files."""
    feedback_dir = arche_dir / "feedback"
    if not feedback_dir.exists():
        return ""
    files = sorted(f for f in feedback_dir.glob("*.yaml") if f.is_file())
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"### {f.name}\n{f.read_text()}")
    return "\n\n".join(parts)


def archive_feedback(arche_dir: Path):
    """Move all feedback files to archive."""
    feedback_dir = arche_dir / "feedback"
    archive_dir = feedback_dir / "archive"
    if not feedback_dir.exists():
        return
    archive_dir.mkdir(exist_ok=True)
    for f in feedback_dir.glob("*.yaml"):
        if f.is_file():
            f.rename(archive_dir / f.name)


def build_system_prompt(arche_dir: Path, mode: str) -> str:
    infinite = (arche_dir / INFINITE).exists()
    step = (arche_dir / STEP_MODE).exists()
    plan_mode = mode == "plan"

    common = Template(read_file(arche_dir / RULE_COMMON) or read_file(PKG_DIR / RULE_COMMON)).render(
        tools=list_tools(arche_dir), project_rules=read_file(arche_dir / PROJECT_RULES)
    )
    rule_file = {"plan": RULE_REVIEW, "exec": RULE_EXEC, "review": RULE_REVIEW, "retro": RULE_RETRO}.get(mode, RULE_EXEC)
    rule = read_file(arche_dir / rule_file) or read_file(PKG_DIR / rule_file)
    prompt = Template(rule).render(infinite=infinite, step=step, common=common, plan_mode=plan_mode)
    return f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{prompt}"


def build_user_prompt(turn: int, arche_dir: Path, goal: str | None, mode: str,
                      next_task: str | None, journal_file: str | None) -> str:
    template = Template(read_file(arche_dir / PROMPT) or read_file(PKG_DIR / PROMPT))
    return template.render(
        turn=turn,
        mode=mode,
        goal=goal,
        feedback=read_feedback(arche_dir),
        prev_journal=read_latest_journal(arche_dir),
        next_task=next_task,
        context_journal=read_latest_journal(arche_dir, journal_file),
    )


def parse_response_json(output: str) -> dict | None:
    if m := re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL):
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for m in re.finditer(r'\{\s*"(?:status|next_task)', output):
        depth, end = 0, m.start()
        for i, c in enumerate(output[m.start():], m.start()):
            depth += (c == '{') - (c == '}')
            if depth == 0:
                end = i + 1
                break
        try:
            return json.loads(output[m.start():end])
        except json.JSONDecodeError:
            continue
    return None


def format_tool_args(name: str, args: dict | None) -> str:
    if not args:
        return ""
    if key := TOOL_ARG_KEYS.get(name):
        val = args.get(key, "")
        if name == "Bash":
            return val[:60] + "..." if len(val) > 60 else val
        if name == "Grep":
            return f'"{val}"'
        return val
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:50] + "..." if len(v) > 50 else v
    return ""


# === Main Loop ===

async def run_loop(arche_dir: Path, goal: str | None = None):
    project_root = arche_dir.parent
    log_file = arche_dir / LOG
    state = read_state(arche_dir)

    infinite = (arche_dir / INFINITE).exists()
    retro_cfg = state.get("retro_every", "auto")
    retro_every = int(retro_cfg) if str(retro_cfg).isdigit() else 0
    turn = state.get("turn", 1)
    plan_mode = state.get("plan_mode", False)
    last_mode = state.get("last_mode")  # Track previous mode
    goal = goal or state.get("goal") or read_goal_from_plan(arche_dir)
    next_task, journal_file = state.get("next_task"), state.get("journal_file")

    engine_cfg = state.get("engine", {})
    engine_type = engine_cfg.get("type", "claude_sdk")
    engine_kwargs = {"cwd": project_root, **engine_cfg.get("kwargs", {})}
    if engine_type == "claude_sdk":
        engine_kwargs["permission_mode"] = "bypassPermissions"

    while True:
        state["turn"] = turn
        write_state(arche_dir, state)

        # Determine natural mode based on previous mode (not turn number)
        if turn == 1:
            natural_mode = "plan" if plan_mode else "exec"
        elif retro_every > 0 and turn % retro_every == 0:
            natural_mode = "retro"
        elif last_mode == "exec":
            natural_mode = "review"
        else:
            # After review/retro/plan, or if unknown → exec
            natural_mode = "exec"

        # Check for forced mode override
        if (arche_dir / FORCE_RETRO).exists():
            (arche_dir / FORCE_RETRO).unlink()
            mode = "retro"
        elif (arche_dir / FORCE_REVIEW).exists():
            (arche_dir / FORCE_REVIEW).unlink()
            mode = "review"
        else:
            mode = natural_mode

        system_prompt = build_system_prompt(arche_dir, mode)
        user_prompt = build_user_prompt(turn, arche_dir, goal, mode, next_task, journal_file)
        engine = create_engine(engine_type, **engine_kwargs)

        try:
            with open(log_file, "a") as f:
                f.write(f"\n{'='*50}\nTurn {turn} ({mode.upper()}) - {datetime.now().isoformat()}\n{'='*50}\n")
                f.flush()

                output, seen_tools, last_was_tool = "", set(), False
                async for event in engine.run(goal=user_prompt, system_prompt=system_prompt):
                    if event.type == EventType.CONTENT and event.content:
                        output += event.content
                        f.write(event.content)
                        f.flush()
                        last_was_tool = False
                    elif event.type == EventType.TOOL_CALL:
                        tool_id = event.metadata.get("tool_id") if event.metadata else None
                        if tool_id and tool_id in seen_tools:
                            continue
                        if tool_id:
                            seen_tools.add(tool_id)
                        prefix = "\n" if not last_was_tool else ""
                        f.write(f"{prefix}[TOOL] {event.tool_name} {format_tool_args(event.tool_name, event.tool_args)}\n")
                        f.flush()
                        last_was_tool = True
                    elif event.type == EventType.ERROR:
                        f.write(f"\n*** Error: {event.error} ***\n")
                        f.flush()
                        last_was_tool = False

                if mode in ("review", "retro", "plan"):
                    if resp := parse_response_json(output):
                        f.write(f"\n*** {mode.upper()}: {resp} ***\n")
                        if not infinite and resp.get("status") == "done":
                            f.write("\n*** Done ***\n")
                            break
                        next_task, journal_file = resp.get("next_task"), resp.get("journal_file")
                    else:
                        f.write(f"\n*** Warning: No {mode} JSON ***\n")
                        next_task, journal_file = None, None
                    # Archive feedback after review/retro/plan completes
                    archive_feedback(arche_dir)
                else:
                    next_task, journal_file = None, None

                # Save state at end of turn (single write)
                last_mode = mode
                state.update(next_task=next_task, journal_file=journal_file, last_mode=last_mode)
                write_state(arche_dir, state)

                turn += 1
                await asyncio.sleep(1)

        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"\n*** Error: {e} ***\n")
            await asyncio.sleep(5)


def daemon_main(arche_dir: Path, goal: str | None):
    (arche_dir / PID).write_text(str(os.getpid()))
    try:
        asyncio.run(run_loop(arche_dir, goal))
    finally:
        (arche_dir / PID).unlink(missing_ok=True)


# === CLI Commands ===

@app.command()
def start(
    goal: list[str] = typer.Argument(..., help="Goal to achieve"),
    engine: str = typer.Option("claude_sdk", "-e", "--engine", help="Engine type"),
    model: str = typer.Option(None, "-m", "--model", help="Model to use"),
    plan: bool = typer.Option(False, "-p", "--plan", help="Start with plan mode"),
    infinite: bool = typer.Option(False, "-i", "--infinite", help="Run infinitely"),
    step: bool = typer.Option(False, "-s", "--step", help="One task at a time"),
    retro_every: str = typer.Option("auto", "-r", "--retro-every", help="Retro schedule"),
    force: bool = typer.Option(False, "-f", "--force", help="Force restart"),
):
    """Start Arche with a goal."""
    goal_str = " ".join(goal)
    arche_dir = Path.cwd() / ".arche"

    if arche_dir.exists():
        running, pid = is_running(arche_dir)
        if running:
            if not force and not typer.confirm(f"Running (PID {pid}). Restart?"):
                typer.echo("Attaching...")
                return tail_log(arche_dir)
            stop_and_wait(arche_dir, pid)
        elif read_state(arche_dir).get("turn", 1) > 1:
            if typer.confirm("Previous session exists. Reset?"):
                reset_arche_dir(arche_dir)

    init_arche_dir(arche_dir)
    write_state(arche_dir, {
        "goal": goal_str,
        "engine": {"type": engine, "kwargs": {"model": model} if model else {}},
        "retro_every": retro_every,
        "turn": 1,
        "plan_mode": plan,
    })

    (arche_dir / INFINITE).touch() if infinite else (arche_dir / INFINITE).unlink(missing_ok=True)
    (arche_dir / STEP_MODE).touch() if step else (arche_dir / STEP_MODE).unlink(missing_ok=True)
    (arche_dir / LOG).write_text(f"Started: {datetime.now().isoformat()}\nGoal: {goal_str}\nEngine: {engine}\n")

    typer.echo(f"Goal: {goal_str}\nEngine: {engine}")
    start_daemon(arche_dir, goal_str)
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
    typer.echo("Stopped." if stop_and_wait(arche_dir, pid) else "Killed.")


@app.command()
def resume(
    feedback_msg: list[str] = typer.Argument(None, help="Optional feedback"),
    review: bool = typer.Option(False, "-r", "--review", help="Force review mode"),
    retro: bool = typer.Option(False, "-R", "--retro", help="Force retro mode"),
    priority: str = typer.Option("medium", "-p", help="Feedback priority"),
):
    """Resume Arche from where it stopped."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)
    if running:
        typer.echo(f"Already running (PID {pid}).")
        return tail_log(arche_dir)

    state = read_state(arche_dir)
    turn = state.get("turn", 1)

    if feedback_msg:
        msg = " ".join(feedback_msg)
        add_feedback(arche_dir, msg, priority)
        typer.echo(f"Feedback: {msg[:50]}...")

    # Auto-enable review mode if there's pending feedback
    if read_feedback(arche_dir):
        review = True

    mode_str = ""
    if retro or review:
        last_mode = state.get("last_mode")

        # Calculate natural mode based on previous mode (not turn number)
        if turn == 1:
            natural = "plan" if state.get("plan_mode") else "exec"
        elif last_mode == "exec":
            natural = "review"
        else:
            natural = "exec"

        forced = "retro" if retro else "review"

        # Only set forced mode if it differs from natural mode
        if forced != natural:
            turn += 1
            state["turn"] = turn
            write_state(arche_dir, state)
            (arche_dir / FORCE_RETRO if retro else FORCE_REVIEW).touch()
            mode_str = f" ({forced})"

    with open(arche_dir / LOG, "a") as f:
        f.write(f"\n{'='*50}\nResumed: {datetime.now().isoformat()} (turn {turn}){mode_str}\n{'='*50}\n")

    typer.echo(f"Resuming turn {turn}{mode_str}...")
    start_daemon(arche_dir)
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
    state = read_state(arche_dir)
    mode = ("infinite" if (arche_dir / INFINITE).exists() else "task")
    mode += " step" if (arche_dir / STEP_MODE).exists() else ""
    typer.echo(f"Dir: {arche_dir}\nStatus: {'Running (PID ' + str(pid) + ')' if running else 'Stopped'}\n"
               f"Engine: {state.get('engine', {}).get('type', 'claude_sdk')}\nTurn: {state.get('turn', 1)}\nMode: {mode}")


@app.command()
def feedback(
    message: list[str] = typer.Argument(..., help="Feedback message"),
    priority: str = typer.Option("medium", "-p", help="Priority: high/medium/low"),
    now: bool = typer.Option(False, "-n", "--now", help="Review now"),
):
    """Add feedback."""
    arche_dir = get_arche_dir()
    msg = " ".join(message)
    add_feedback(arche_dir, msg, priority)
    typer.echo("Feedback added.")

    if now:
        (arche_dir / FORCE_REVIEW).touch()
        running, pid = is_running(arche_dir)
        if running:
            stop_and_wait(arche_dir, pid)
        typer.echo("Starting review...")
        start_daemon(arche_dir)
        time.sleep(0.5)
        tail_log(arche_dir)


@app.command()
def version():
    """Show version."""
    from arche import __version__
    typer.echo(f"arche {__version__}")


@app.command(name="daemon", hidden=True)
def daemon_cmd(arche_dir: str, goal_b64: str):
    """Internal daemon entry."""
    daemon_main(Path(arche_dir), base64.b64decode(goal_b64).decode() or None)


@app.command(name="serve")
def serve_cmd(
    host: str = typer.Option("0.0.0.0", "-h", "--host", help="Bind host"),
    port: int = typer.Option(8420, "-p", "--port", help="Bind port"),
    password: str = typer.Option(None, "-P", "--password", help="Auth password"),
    reload: bool = typer.Option(False, "-r", "--reload", help="Auto-reload"),
):
    """Start web UI server."""
    from arche.server.daemon import run_daemon
    run_daemon(project_path=Path.cwd(), host=host, port=port, password=password, reload=reload)


if __name__ == "__main__":
    app()
