"""Arche Daemon Mode - Start FastAPI server with uvicorn."""

import os
import sys
from pathlib import Path

import typer
import uvicorn

from arche.server.app import app, setup_server


def run_daemon(
    project_path: Path = Path.cwd(),
    host: str = "0.0.0.0",
    port: int = 8420,
    password: str | None = None,
    reload: bool = False,
):
    """Run Arche in daemon mode with web UI."""
    # Setup server config
    setup_server(project_path, password)

    print(f"\033[38;5;208m╔══════════════════════════════════════════════════════════════╗\033[0m")
    print(f"\033[38;5;208m║\033[0m  \033[1;97mARCHE DAEMON\033[0m                                               \033[38;5;208m║\033[0m")
    print(f"\033[38;5;208m╠══════════════════════════════════════════════════════════════╣\033[0m")
    print(f"\033[38;5;208m║\033[0m  Project: \033[96m{str(project_path)[:48]:<48}\033[0m \033[38;5;208m║\033[0m")
    print(f"\033[38;5;208m║\033[0m  Server:  \033[92mhttp://{host}:{port}\033[0m{' ' * (47 - len(f'{host}:{port}'))}\033[38;5;208m║\033[0m")
    print(f"\033[38;5;208m║\033[0m  Auth:    \033[{'93mEnabled' if password else '91mDisabled':<47}\033[0m \033[38;5;208m║\033[0m")
    print(f"\033[38;5;208m╚══════════════════════════════════════════════════════════════╝\033[0m")
    print()

    uvicorn.run(
        "arche.server.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# CLI integration
daemon_app = typer.Typer(name="daemon", help="Run Arche in daemon mode with web UI")


@daemon_app.command("start")
def start(
    host: str = typer.Option("0.0.0.0", "-h", "--host", help="Bind host"),
    port: int = typer.Option(8420, "-p", "--port", help="Bind port"),
    password: str = typer.Option(None, "--password", "-P", help="Auth password"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """Start Arche daemon server."""
    run_daemon(
        project_path=Path.cwd(),
        host=host,
        port=port,
        password=password,
        reload=reload,
    )


if __name__ == "__main__":
    daemon_app()
