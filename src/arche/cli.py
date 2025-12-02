#!/usr/bin/env python3
"""Arche - Long-lived coding agent runner for Claude Code."""

import base64
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import typer
from jinja2 import Template

app = typer.Typer(
    name="arche",
    help="Long-lived coding agent that runs Claude Code in exec/review alternation.",
    no_args_is_help=True,
    add_completion=False,
)

# File names
LOG, PID, RULE_EXEC, RULE_REVIEW, RULE_COMMON, PROMPT = "arche.log", "arche.pid", "RULE_EXEC.md", "RULE_REVIEW.md", "RULE_COMMON.md", "PROMPT.md"
INFINITE, FORCE_REVIEW, CLAUDE_ARGS, BATCH_MODE = "infinite", "force_review", "claude_args.json", "batch"
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
    """List tools in .arche/tools/ (filenames are self-descriptive)."""
    tools_dir = arche_dir / "tools"
    if not tools_dir.exists():
        return ""
    tools = [f.stem for f in sorted(tools_dir.glob("*.py"))]
    return ", ".join(tools) if tools else ""


def read_latest_journal(arche_dir: Path, journal_path: str | None = None) -> str:
    """Read specific or latest journal."""
    if journal_path and (arche_dir / journal_path).exists():
        return (arche_dir / journal_path).read_text()
    journals = sorted((arche_dir / "journal").glob("*.yaml"), reverse=True) if (arche_dir / "journal").exists() else []
    return journals[0].read_text() if journals else ""


def parse_reviewer_json(output: str) -> dict | None:
    """Parse JSON from reviewer output."""
    for pattern in [r'```json\s*(\{.*?\})\s*```', r'(\{\s*"(?:status|next_task)".*?\})']:
        if m := re.search(pattern, output, re.DOTALL):
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


def build_prompt(turn: int, arche_dir: Path, goal: str | None, review_mode: bool,
                 next_task: str | None, journal_file: str | None, resumed: bool) -> str:
    """Build user prompt from template."""
    tpl = Template(read_file(PKG_DIR / PROMPT) or "Turn {{ turn }}.")
    if review_mode:
        return tpl.render(turn=turn, goal=goal, review_mode=True,
                         prev_journal=read_latest_journal(arche_dir), resumed=resumed)
    return tpl.render(turn=turn, goal=goal, review_mode=False,
                     next_task=next_task or goal or "Continue with the plan",
                     context_journal=read_latest_journal(arche_dir, journal_file) if journal_file else "")


def build_cmd(turn: int, arche_dir: Path, goal: str | None, extra_args: list[str] | None,
              review_mode: bool, next_task: str | None, journal_file: str | None, resumed: bool) -> list[str]:
    """Build claude CLI command."""
    infinite = (arche_dir / INFINITE).exists()
    batch = (arche_dir / BATCH_MODE).exists()
    tools = list_tools(arche_dir)
    rule_file = arche_dir / (RULE_REVIEW if review_mode else RULE_EXEC)
    common = Template(read_file(arche_dir / RULE_COMMON) or read_file(PKG_DIR / RULE_COMMON)).render(tools=tools)

    cmd = ["claude", "--print", "--permission-mode", "plan"]
    if rule_file.exists():
        cmd.extend(["--system-prompt", Template(rule_file.read_text()).render(infinite=infinite, batch=batch, common=common)])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(build_prompt(turn, arche_dir, goal, review_mode, next_task, journal_file, resumed))
    return cmd


def run_loop(arche_dir: Path, goal: str | None = None, extra_args: list[str] | None = None):
    """Main exec/review loop."""
    log_file, infinite, turn = arche_dir / LOG, (arche_dir / INFINITE).exists(), 1
    next_task, journal_file = None, None

    while True:
        # Check forced review
        force_file = arche_dir / FORCE_REVIEW
        if force_file.exists():
            force_file.unlink()
            review_mode, resumed = True, True
        else:
            review_mode, resumed = (turn % 2 == 0), False

        cmd = build_cmd(turn, arche_dir, goal if turn == 1 else None, extra_args,
                       review_mode, next_task, journal_file, resumed)

        try:
            with open(log_file, "a") as f:
                f.write(f"\n{'='*50}\nTurn {turn} ({'REVIEW' if review_mode else 'EXEC'}) - {datetime.now().isoformat()}\n{'='*50}\n")
                f.flush()

                proc = subprocess.Popen(cmd, cwd=str(arche_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output = ""
                while chunk := proc.stdout.read(1):
                    output += (d := chunk.decode('utf-8', errors='replace'))
                    f.write(d)
                    f.flush()
                proc.wait()

                if review_mode:
                    if resp := parse_reviewer_json(output):
                        f.write(f"\n*** Reviewer: {resp} ***\n")
                        if not infinite and resp.get("status") == "done":
                            f.write("\n*** Done ***\n")
                            break
                        next_task, journal_file = resp.get("next_task"), resp.get("journal_file")
                    else:
                        f.write("\n*** Warning: No reviewer JSON ***\n")
                        next_task, journal_file = None, None

                if proc.returncode != 0:
                    f.write(f"\n*** Failed (code {proc.returncode}) ***\n")
                    time.sleep(5)
                turn += 1
                time.sleep(1)
        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"\n*** Error: {e} ***\n")
            time.sleep(5)


def daemon_main(arche_dir: Path, goal: str | None = None, extra_args: list[str] | None = None):
    """Daemon entry point."""
    pid_file = arche_dir / PID
    pid_file.write_text(str(os.getpid()))
    try:
        run_loop(arche_dir, goal, extra_args)
    finally:
        pid_file.unlink(missing_ok=True)


def start_daemon(arche_dir: Path, goal: str | None, extra_args: list[str]):
    """Start daemon process."""
    goal_b64 = base64.b64encode((goal or "").encode()).decode()
    args_b64 = base64.b64encode(json.dumps(extra_args).encode()).decode()
    subprocess.Popen(
        [sys.executable, "-c", f"""
import sys, base64, json; sys.path.insert(0, '{PKG_DIR.parent}')
from arche.cli import daemon_main; from pathlib import Path
g = base64.b64decode('{goal_b64}').decode() or None
a = json.loads(base64.b64decode('{args_b64}').decode())
daemon_main(Path('{arche_dir}'), g, a)
"""],
        start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def tail_log(arche_dir: Path):
    """Tail log file."""
    log_file = arche_dir / LOG
    if not log_file.exists():
        log_file.write_text("")
    try:
        subprocess.run(["tail", "-f", "-n", "100", str(log_file)])
    except KeyboardInterrupt:
        typer.echo("\nDetached. Arche continues in background.", err=True)


@app.command(context_settings={"allow_extra_args": True, "allow_interspersed_args": False})
def start(
    ctx: typer.Context,
    goal: str = typer.Argument(..., help="Goal for Arche to achieve"),
    infinite: bool = typer.Option(False, "-i", "--infinite", help="Run infinitely"),
    batch: bool = typer.Option(False, "-b", "--batch", help="Exec all tasks at once (no incremental)"),
    force: bool = typer.Option(False, "-f", "--force", help="Restart if running"),
):
    """Start Arche. Extra args after -- go to claude CLI."""
    if not shutil.which("claude"):
        typer.echo("Error: claude CLI not found.", err=True)
        raise typer.Exit(1)

    arche_dir = Path.cwd() / ".arche"
    extra_args = ctx.args

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
    for rf in [RULE_EXEC, RULE_REVIEW, RULE_COMMON]:
        dest = arche_dir / rf
        if not dest.exists() or force:
            dest.write_text(read_file(PKG_DIR / rf))

    (arche_dir / INFINITE).touch() if infinite else (arche_dir / INFINITE).unlink(missing_ok=True)
    (arche_dir / BATCH_MODE).touch() if batch else (arche_dir / BATCH_MODE).unlink(missing_ok=True)
    (arche_dir / CLAUDE_ARGS).write_text(json.dumps(extra_args)) if extra_args else (arche_dir / CLAUDE_ARGS).unlink(missing_ok=True)
    (arche_dir / LOG).write_text(f"Started: {datetime.now().isoformat()}\nGoal: {goal}\n")

    typer.echo(f"Goal: {goal}")
    start_daemon(arche_dir, goal, extra_args)
    time.sleep(0.5)
    tail_log(arche_dir)


@app.command()
def stop():
    """Stop Arche and Claude subprocess."""
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

    extra_args = json.loads(read_file(arche_dir / CLAUDE_ARGS) or "[]")
    (arche_dir / FORCE_REVIEW).touch()

    with open(arche_dir / LOG, "a") as f:
        f.write(f"\n{'='*50}\nResumed: {datetime.now().isoformat()}\n{'='*50}\n")

    typer.echo("Resuming (review mode)...")
    start_daemon(arche_dir, None, extra_args)
    time.sleep(0.5)
    tail_log(arche_dir)


@app.command()
def log(
    follow: bool = typer.Option(True, "-f/--no-follow", help="Follow in real-time"),
    lines: int = typer.Option(100, "-n", "--lines", help="Lines to show"),
    clear: bool = typer.Option(False, "-c", "--clear", help="Clear log"),
):
    """Show logs (real-time by default)."""
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
    """Show status (running/stopped, mode)."""
    if not (arche_dir := find_arche_dir()):
        return typer.echo("No .arche/ found.")
    running, pid = is_running(arche_dir)
    mode = ("infinite" if (arche_dir / INFINITE).exists() else "task") + (" batch" if (arche_dir / BATCH_MODE).exists() else "")
    typer.echo(f"Dir: {arche_dir}")
    typer.echo(f"Status: {'Running (PID ' + str(pid) + ')' if running else 'Stopped'}")
    typer.echo(f"Mode: {mode}")


@app.command()
def feedback(
    message: str = typer.Argument(..., help="Feedback message"),
    priority: str = typer.Option("medium", "-p", help="high/medium/low"),
    now: bool = typer.Option(False, "-n", "--now", help="Interrupt and review now"),
):
    """Add feedback. Use --now to interrupt current task."""
    arche_dir = get_arche_dir()
    pending = arche_dir / "feedback" / "pending"
    pending.mkdir(parents=True, exist_ok=True)

    ts = datetime.now()
    slug = re.sub(r'[^a-z0-9-]', '-', message[:30].lower())
    (pending / f"{ts:%Y%m%d-%H%M}-{slug}.yaml").write_text(
        f'meta:\n  timestamp: "{ts.isoformat()}"\nsummary: "{message}"\npriority: "{priority}"\nstatus: "pending"\n'
    )
    typer.echo(f"Feedback added.")

    if now:
        (arche_dir / FORCE_REVIEW).touch()
        running, pid = is_running(arche_dir)
        if running:
            typer.echo(f"Interrupting PID {pid}...")
            kill_arche(pid)
        else:
            typer.echo("Not running. Use 'arche resume'.")


@app.command()
def version():
    """Show version."""
    from arche import __version__
    typer.echo(f"arche {__version__}")


if __name__ == "__main__":
    app()
