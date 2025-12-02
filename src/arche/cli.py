#!/usr/bin/env python3
"""Arche - Long-lived coding agent runner."""

import asyncio
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
LOG, PID, SERVER_PID, STATE = "arche.log", "arche.pid", "server.pid", "state.json"
TEMPLATES = ["RULE_EXEC.md", "RULE_REVIEW.md", "RULE_RETRO.md", "RULE_COMMON.md", "RULE_PROJECT.md", "PROMPT.md", "CHECKLIST.yaml"]
INFINITE, FORCE_REVIEW, FORCE_RETRO, STEP_MODE = "infinite", "force_review", "force_retro", "step"
PKG_DIR = Path(__file__).parent
TPL_DIR = PKG_DIR / "templates"
DIRS = ["journal", "plan", "feedback", "feedback/archive", "retrospective", "tools", "templates"]

# Tool arg display keys
TOOL_ARG_KEYS = {
    "Read": "file_path", "Write": "file_path", "Edit": "file_path",
    "Bash": "command", "Grep": "pattern", "Glob": "pattern", "Task": "description",
}


# === Utilities ===

def read_file(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def get_template(arche_dir: Path | None, name: str) -> str:
    """Get template content. Checks .arche/templates first, falls back to package."""
    if arche_dir and (arche_dir / "templates" / name).exists():
        return (arche_dir / "templates" / name).read_text()
    return (TPL_DIR / name).read_text()


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


def check_pid(pid_file: Path) -> tuple[bool, int | None]:
    """Check if process is running by PID file."""
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return False, None


def is_running(arche_dir: Path) -> tuple[bool, int | None]:
    return check_pid(arche_dir / PID)


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
    # Copy RULE_PROJECT.md by default (can be customized)
    rules_file = arche_dir / "templates" / "RULE_PROJECT.md"
    if not rules_file.exists():
        rules_file.write_text((TPL_DIR / "RULE_PROJECT.md").read_text())


def reset_arche_dir(arche_dir: Path):
    """Reset .arche/ preserving templates/."""
    templates = {}
    tpl_dir = arche_dir / "templates"
    if tpl_dir.exists():
        for f in tpl_dir.iterdir():
            if f.is_file():
                templates[f.name] = f.read_text()
    shutil.rmtree(arche_dir)
    init_arche_dir(arche_dir)
    for name, content in templates.items():
        (arche_dir / "templates" / name).write_text(content)


def start_daemon(arche_dir: Path):
    subprocess.Popen(
        [sys.executable, "-m", "arche.cli", "daemon", str(arche_dir)],
        start_new_session=True, stdout=subprocess.DEVNULL,
        stderr=open(arche_dir / "daemon.err", "a"),
    )


def start_session(arche_dir: Path, goal: str, engine: str, model: str | None,
                  plan_mode: bool, infinite: bool, step: bool, retro_every: str):
    """Initialize and start a new agent session."""
    init_arche_dir(arche_dir)
    write_state(arche_dir, {
        "engine": {"type": engine, "kwargs": {"model": model} if model else {}},
        "retro_every": retro_every,
        "turn": 1,
        "plan_mode": plan_mode,
    })
    add_feedback(arche_dir, goal, "goal")

    (arche_dir / INFINITE).touch() if infinite else (arche_dir / INFINITE).unlink(missing_ok=True)
    (arche_dir / STEP_MODE).touch() if step else (arche_dir / STEP_MODE).unlink(missing_ok=True)
    (arche_dir / LOG).write_text(f"Started: {datetime.now().isoformat()}\nGoal: {goal}\nEngine: {engine}\n")

    start_daemon(arche_dir)


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


def load_checklist(arche_dir: Path | None = None) -> dict:
    """Load done checklist from YAML."""
    return yaml.safe_load(get_template(arche_dir, "CHECKLIST.yaml")) or {}


def build_system_prompt(arche_dir: Path, mode: str) -> str:
    infinite = (arche_dir / INFINITE).exists()
    step = (arche_dir / STEP_MODE).exists()
    plan_mode = mode == "plan"
    checklist = load_checklist(arche_dir)

    common = Template(get_template(arche_dir, "RULE_COMMON.md")).render(
        tools=list_tools(arche_dir), project_rules=get_template(arche_dir, "RULE_PROJECT.md")
    )
    rule_map = {"plan": "RULE_REVIEW.md", "exec": "RULE_EXEC.md", "review": "RULE_REVIEW.md", "retro": "RULE_RETRO.md"}
    rule = get_template(arche_dir, rule_map.get(mode, "RULE_EXEC.md"))
    prompt = Template(rule).render(infinite=infinite, step=step, common=common, plan_mode=plan_mode, checklist=checklist)
    return f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{prompt}"


def build_user_prompt(turn: int, arche_dir: Path, mode: str,
                      next_task: str | None, journal_file: str | None) -> str:
    template = Template(get_template(arche_dir, "PROMPT.md"))
    return template.render(
        turn=turn,
        mode=mode,
        goal=read_goal_from_plan(arche_dir),  # From plan, not state
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

async def run_loop(arche_dir: Path):
    project_root = arche_dir.parent
    log_file = arche_dir / LOG
    state = read_state(arche_dir)

    infinite = (arche_dir / INFINITE).exists()
    retro_cfg = state.get("retro_every", "auto")
    retro_every = int(retro_cfg) if str(retro_cfg).isdigit() else 0
    turn = state.get("turn", 1)
    plan_mode = state.get("plan_mode", False)
    last_mode = state.get("last_mode")  # Track previous mode
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
        user_prompt = build_user_prompt(turn, arche_dir, mode, next_task, journal_file)
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
                            cl = resp.get("checklist", {})
                            missing = [k for k in load_checklist(arche_dir) if not cl.get(k)]
                            if not missing:
                                f.write("\n*** Done ***\n")
                                archive_feedback(arche_dir)
                                break
                            f.write(f"\n*** Done rejected: missing {missing} ***\n")
                            next_task = f"Complete checklist: {missing}"
                        else:
                            next_task = resp.get("next_task")
                        journal_file = resp.get("journal_file")
                    else:
                        f.write(f"\n*** Warning: No {mode} JSON ***\n")
                        next_task, journal_file = None, None
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


def daemon_main(arche_dir: Path):
    (arche_dir / PID).write_text(str(os.getpid()))
    try:
        asyncio.run(run_loop(arche_dir))
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

    start_session(arche_dir, goal_str, engine, model, plan, infinite, step, retro_every)
    typer.echo(f"Goal: {goal_str}\nEngine: {engine}")
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


@app.command()
def templates(
    list_only: bool = typer.Option(False, "-l", "--list", help="List templates only"),
):
    """Copy default templates to .arche/templates/ for customization."""
    arche_dir = Path.cwd() / ".arche"
    tpl_dest = arche_dir / "templates"
    tpl_dest.mkdir(parents=True, exist_ok=True)

    if list_only:
        typer.echo("Available templates:")
        for name in TEMPLATES:
            exists = "✓" if (tpl_dest / name).exists() else " "
            typer.echo(f"  [{exists}] {name}")
        return

    copied, skipped = 0, 0
    for name in TEMPLATES:
        dest = tpl_dest / name
        if dest.exists():
            skipped += 1
        else:
            dest.write_text((TPL_DIR / name).read_text())
            copied += 1
            typer.echo(f"  + {name}")

    typer.echo(f"Copied {copied}, skipped {skipped} (already exist)")


@app.command(name="daemon", hidden=True)
def daemon_cmd(arche_dir: str):
    """Internal daemon entry."""
    daemon_main(Path(arche_dir))


# === Serve subcommands ===
serve_app = typer.Typer(name="serve", help="Web UI server commands", no_args_is_help=True)
app.add_typer(serve_app)


def _stop_server(arche_dir: Path) -> bool:
    """Stop server if running. Returns True if was running."""
    running, pid = check_pid(arche_dir / SERVER_PID)
    if not running:
        return False
    typer.echo(f"Stopping server (PID {pid})...")
    kill_process(pid)
    time.sleep(1)
    (arche_dir / SERVER_PID).unlink(missing_ok=True)
    return True


def _start_server(arche_dir: Path, host: str, port: int, password: str | None) -> bool:
    """Start server daemon. Returns True if started successfully."""
    arche_dir.mkdir(exist_ok=True)
    subprocess.Popen(
        [sys.executable, "-m", "arche.cli", "_serve_daemon", str(arche_dir), host, str(port), password or ""],
        start_new_session=True, stdout=subprocess.DEVNULL,
        stderr=open(arche_dir / "server.err", "a"),
    )
    time.sleep(1)
    if check_pid(arche_dir / SERVER_PID)[0]:
        typer.echo(f"Server started at http://{host}:{port}")
        return True
    typer.echo("Failed to start. Check: arche serve log", err=True)
    return False


@serve_app.command(name="start")
def serve_start(
    host: str = typer.Option("0.0.0.0", "-h", "--host", help="Bind host"),
    port: int = typer.Option(8420, "-p", "--port", help="Bind port"),
    password: str = typer.Option(None, "-P", "--password", help="Auth password"),
    foreground: bool = typer.Option(False, "-f", "--foreground", help="Run in foreground"),
):
    """Start web UI server."""
    arche_dir = Path.cwd() / ".arche"
    running, pid = check_pid(arche_dir / SERVER_PID)
    if running:
        typer.echo(f"Server already running (PID {pid}). Use 'arche serve restart'.")
        return

    if foreground:
        from arche.server.daemon import run_daemon
        run_daemon(project_path=Path.cwd(), host=host, port=port, password=password, reload=True)
    else:
        _start_server(arche_dir, host, port, password)


@serve_app.command(name="stop")
def serve_stop():
    """Stop web UI server."""
    if _stop_server(Path.cwd() / ".arche"):
        typer.echo("Stopped.")
    else:
        typer.echo("Server not running.", err=True)
        raise typer.Exit(1)


@serve_app.command(name="restart")
def serve_restart(
    host: str = typer.Option("0.0.0.0", "-h", "--host", help="Bind host"),
    port: int = typer.Option(8420, "-p", "--port", help="Bind port"),
    password: str = typer.Option(None, "-P", "--password", help="Auth password"),
):
    """Restart web UI server."""
    arche_dir = Path.cwd() / ".arche"
    _stop_server(arche_dir)
    _start_server(arche_dir, host, port, password)


@serve_app.command(name="status")
def serve_status():
    """Show server status."""
    running, pid = check_pid(Path.cwd() / ".arche" / SERVER_PID)
    typer.echo(f"Running (PID {pid})" if running else "Stopped")


@serve_app.command(name="log")
def serve_log(
    lines: int = typer.Option(50, "-n", "--lines", help="Lines to show"),
    error: bool = typer.Option(False, "-e", "--error", help="Show only error log"),
):
    """Show server logs."""
    err_file = Path.cwd() / ".arche" / "server.err"
    if not err_file.exists() or err_file.stat().st_size == 0:
        typer.echo("No server logs.")
        return
    content = err_file.read_text()
    output = "\n".join(content.strip().split('\n')[-lines:]) if not error else content[-5000:]
    typer.echo(output)


@app.command(name="_serve_daemon", hidden=True)
def serve_daemon_cmd(arche_dir: str, host: str, port: str, password: str):
    """Internal server daemon entry."""
    arche_path = Path(arche_dir)
    (arche_path / SERVER_PID).write_text(str(os.getpid()))
    try:
        from arche.server.daemon import run_daemon
        run_daemon(project_path=arche_path.parent, host=host, port=int(port), password=password or None, reload=False)
    finally:
        (arche_path / SERVER_PID).unlink(missing_ok=True)


if __name__ == "__main__":
    app()
