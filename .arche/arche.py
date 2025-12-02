#!/usr/bin/env python3
"""Arche - Long-lived coding agent runner for Claude Code."""

import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="arche",
    help="Long-lived coding agent that runs Claude Code in a loop.",
    no_args_is_help=True,
)

ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"

DEFAULT_PROMPT = (
    "Arche turn {turn}. Follow CLAUDE.md. "
    "Output ARCHE_DONE when current task is complete."
)


def ensure_claude_available() -> None:
    if shutil.which("claude") is None:
        typer.echo("Error: `claude` CLI not found in PATH.", err=True)
        raise typer.Exit(1)


def build_claude_cmd(turn: int, prompt_template: str, extra_args: str) -> list[str]:
    """Build the claude CLI command for a single turn."""
    cmd: list[str] = [
        "claude", "--print",
        "--add-dir", "..",
        "--dangerously-skip-permissions",
    ]

    if extra_args:
        cmd.extend(shlex.split(extra_args))

    prompt = prompt_template.format(turn=turn)
    cmd.append(prompt)
    return cmd


def index_worker(interval_sec: int) -> None:
    """Background loop that runs tools/embed_yaml.py if present."""
    while True:
        try:
            embed_script = TOOLS_DIR / "embed_yaml.py"
            if embed_script.exists():
                subprocess.run(
                    [sys.executable, str(embed_script)],
                    cwd=str(ROOT),
                    check=False,
                    capture_output=True,
                )
        except Exception:
            pass
        time.sleep(interval_sec)


def run_claude_with_output(cmd: list[str]) -> tuple[int, str, bool]:
    """Run claude and stream output with ANSI colors. Returns (returncode, output, is_done)."""
    full_output = ""
    is_done = False

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Read byte by byte for real-time output with ANSI
    while True:
        chunk = proc.stdout.read(1)
        if not chunk:
            break
        # Write to terminal immediately (preserves ANSI)
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        # Accumulate for ARCHE_DONE check
        try:
            full_output += chunk.decode('utf-8', errors='replace')
        except:
            pass

    proc.wait()

    if "ARCHE_DONE" in full_output:
        is_done = True

    return proc.returncode, full_output, is_done


@app.command()
def run(
    infinite: bool = typer.Option(False, "--infinite", "-i", help="Run infinitely, self-improving after task completion"),
    turns: int = typer.Option(1, "--turns", "-n", help="Number of turns to run (ignored if --infinite)"),
    start_turn: int = typer.Option(1, "--start", "-s", help="Starting turn number"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Custom prompt template"),
    extra_args: str = typer.Option("", "--claude-args", "-a", help="Extra args for claude CLI"),
    index_interval: int = typer.Option(60, "--index-interval", help="Index worker interval in seconds"),
    no_index: bool = typer.Option(False, "--no-index", help="Disable background indexing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Run Arche agent for one or more turns."""
    ensure_claude_available()

    if not no_index:
        threading.Thread(target=index_worker, args=(index_interval,), daemon=True).start()

    prompt_template = prompt or DEFAULT_PROMPT
    turn = start_turn
    runs = 0

    while True:
        if verbose:
            typer.echo(f"--- Turn {turn} ---", err=True)

        cmd = build_claude_cmd(turn, prompt_template, extra_args)

        try:
            returncode, output, is_done = run_claude_with_output(cmd)

            turn += 1
            runs += 1

            if returncode != 0:
                typer.echo(f"\nTurn {turn-1} failed (code {returncode})", err=True)
                time.sleep(2)

            # Exit conditions
            if is_done and not infinite:
                typer.echo("Arche completed (ARCHE_DONE).", err=True)
                break
            if not infinite and runs >= turns:
                break

            time.sleep(1)

        except KeyboardInterrupt:
            typer.echo("\nArche stopped by user.", err=True)
            break
        except Exception as e:
            typer.echo(f"Arche error: {e}", err=True)
            time.sleep(5)


@app.command()
def task(
    description: str = typer.Argument(..., help="Task description for Arche"),
    infinite: bool = typer.Option(False, "--infinite", "-i", help="Keep running, self-improve after completion"),
    max_turns: int = typer.Option(10, "--max-turns", "-n", help="Max turns before stopping"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Run a single task. Stops on ARCHE_DONE or max turns (unless --infinite)."""
    task_prompt = (
        "Arche turn {{turn}}. Task: {task}. "
        "Output ARCHE_DONE when this task is complete."
    ).format(task=description)

    run(infinite=infinite, turns=max_turns, start_turn=1, prompt=task_prompt,
        extra_args="", index_interval=60, no_index=False, verbose=verbose)


@app.command()
def version():
    """Show version."""
    typer.echo("arche 0.1.0")


if __name__ == "__main__":
    app()
