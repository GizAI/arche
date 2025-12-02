"""Arche FastAPI Server - Web UI backend.

Architecture: Imports utilities from arche.cli - no code duplication.
"""

import asyncio
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import utilities from cli - no duplication
from arche.cli import (
    LOG,
    INFINITE,
    FORCE_REVIEW,
    FORCE_RETRO,
    STEP_MODE,
    read_state,
    write_state,
    is_running,
    read_feedback,
    init_arche_dir,
    start_daemon,
    stop_and_wait,
    start_session,
    read_goal_from_plan,
    add_feedback,
)

# FastAPI app
app = FastAPI(title="Arche", version="0.1.0")

# Config - set by setup_server()
_config: dict[str, Any] = {
    "project_path": None,
    "arche_dir": None,
    "password": None,
}

# Security
security = HTTPBasic(auto_error=False)


def setup_server(project_path: Path, password: str | None = None):
    """Configure server with project path and optional auth."""
    _config["project_path"] = project_path
    _config["arche_dir"] = project_path / ".arche"
    _config["password"] = password

    # Ensure .arche dir exists
    init_arche_dir(_config["arche_dir"])


def get_arche_dir() -> Path:
    """Get configured .arche directory."""
    if not _config["arche_dir"]:
        raise HTTPException(500, "Server not configured")
    return _config["arche_dir"]


def verify_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> bool:
    """Verify HTTP Basic auth if password is set."""
    if not _config["password"]:
        return True
    if not credentials:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Basic"})
    if not secrets.compare_digest(credentials.password, _config["password"]):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return True


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Pydantic Models ===

class StatusResponse(BaseModel):
    running: bool
    pid: int | None
    turn: int
    goal: str | None
    mode: str
    engine: str
    last_mode: str | None
    infinite: bool
    step: bool
    paused: bool


class StartRequest(BaseModel):
    goal: str
    engine: str = "claude_sdk"
    model: str | None = None
    plan_mode: bool = False
    infinite: bool = False
    step: bool = False
    retro_every: str = "auto"


class FeedbackRequest(BaseModel):
    message: str
    priority: str = "medium"
    interrupt: bool = False


class FileContent(BaseModel):
    path: str
    content: str


# === API Routes ===

@app.get("/api/status", response_model=StatusResponse)
async def get_status(auth: bool = Depends(verify_auth)):
    """Get agent status."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)
    state = read_state(arche_dir)

    return StatusResponse(
        running=running,
        pid=pid,
        turn=state.get("turn", 1),
        goal=read_goal_from_plan(arche_dir),
        mode="plan" if state.get("plan_mode") else "exec",
        engine=state.get("engine", {}).get("type", "claude_sdk"),
        last_mode=state.get("last_mode"),
        infinite=(arche_dir / INFINITE).exists(),
        step=(arche_dir / STEP_MODE).exists(),
        paused=(arche_dir / "paused").exists(),
    )


@app.post("/api/start")
async def start_agent(req: StartRequest, auth: bool = Depends(verify_auth)):
    """Start the agent."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)

    if running:
        raise HTTPException(409, f"Agent already running (PID {pid})")

    # Use shared start_session helper
    start_session(arche_dir, req.goal, req.engine, req.model,
                  req.plan_mode, req.infinite, req.step, req.retro_every)

    return {"status": "started", "goal": req.goal}


@app.post("/api/stop")
async def stop_agent(auth: bool = Depends(verify_auth)):
    """Stop the agent."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)

    if not running:
        raise HTTPException(409, "Agent not running")

    graceful = stop_and_wait(arche_dir, pid)
    return {"status": "stopped", "graceful": graceful}


@app.post("/api/resume")
async def resume_agent(
    review: bool = False,
    retro: bool = False,
    auth: bool = Depends(verify_auth),
):
    """Resume a stopped agent."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)

    if running:
        raise HTTPException(409, f"Agent already running (PID {pid})")

    state = read_state(arche_dir)
    turn = state.get("turn", 1)

    # Auto-enable review mode if there's pending feedback
    if read_feedback(arche_dir):
        review = True

    # Handle forced modes (match CLI logic)
    if retro or review:
        last_mode = state.get("last_mode")

        # Calculate natural mode based on previous mode
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

    # Remove paused flag if present
    (arche_dir / "paused").unlink(missing_ok=True)

    # Log resume
    with open(arche_dir / LOG, "a") as f:
        mode_str = " (retro)" if retro else " (review)" if review else ""
        f.write(f"\n{'='*50}\nResumed: {datetime.now().isoformat()} (turn {turn}){mode_str}\n{'='*50}\n")

    start_daemon(arche_dir)
    return {"status": "resumed", "turn": turn}


@app.post("/api/pause")
async def pause_agent(auth: bool = Depends(verify_auth)):
    """Pause agent after current turn."""
    arche_dir = get_arche_dir()
    running, _ = is_running(arche_dir)

    if not running:
        raise HTTPException(409, "Agent not running")

    (arche_dir / "paused").touch()
    return {"status": "paused"}


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest, auth: bool = Depends(verify_auth)):
    """Submit feedback."""
    arche_dir = get_arche_dir()
    add_feedback(arche_dir, req.message, req.priority)

    if req.interrupt:
        (arche_dir / FORCE_REVIEW).touch()
        running, pid = is_running(arche_dir)
        if running:
            stop_and_wait(arche_dir, pid)
            start_daemon(arche_dir)

    return {"status": "submitted", "interrupt": req.interrupt}


# === File Browser API ===

@app.get("/api/files")
async def list_files(auth: bool = Depends(verify_auth)):
    """List .arche directory tree."""
    arche_dir = get_arche_dir()

    def scan_dir(path: Path, base: Path) -> list[dict]:
        items = []
        try:
            for entry in sorted(path.iterdir()):
                rel_path = str(entry.relative_to(base))
                if entry.is_dir():
                    items.append({
                        "name": entry.name,
                        "path": rel_path,
                        "type": "directory",
                        "children": scan_dir(entry, base),
                    })
                else:
                    items.append({
                        "name": entry.name,
                        "path": rel_path,
                        "type": "file",
                        "size": entry.stat().st_size,
                        "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                    })
        except PermissionError:
            pass
        return items

    return {"root": ".arche", "items": scan_dir(arche_dir, arche_dir)}


@app.get("/api/files/{path:path}")
async def read_file(path: str, auth: bool = Depends(verify_auth)):
    """Read file content from .arche directory."""
    arche_dir = get_arche_dir()
    file_path = arche_dir / path

    # Security: ensure path stays within .arche
    try:
        file_path = file_path.resolve()
        arche_dir.resolve()
        if not str(file_path).startswith(str(arche_dir.resolve())):
            raise HTTPException(403, "Access denied")
    except Exception:
        raise HTTPException(403, "Invalid path")

    if not file_path.exists():
        raise HTTPException(404, "File not found")

    if not file_path.is_file():
        raise HTTPException(400, "Not a file")

    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        raise HTTPException(400, "Binary file not supported")

    return {"path": path, "content": content}


@app.put("/api/files/{path:path}")
async def write_file(path: str, file: FileContent, auth: bool = Depends(verify_auth)):
    """Write file content to .arche directory."""
    arche_dir = get_arche_dir()
    file_path = arche_dir / path

    # Security: ensure path stays within .arche
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(arche_dir.resolve())):
            raise HTTPException(403, "Access denied")
    except Exception:
        raise HTTPException(403, "Invalid path")

    # Create parent dirs if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(file.content)

    return {"status": "saved", "path": path}


# === WebSocket Endpoints ===

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {"logs": [], "events": []}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if websocket in self.active_connections[channel]:
            self.active_connections[channel].remove(websocket)

    async def broadcast(self, message: dict, channel: str):
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection, channel)


manager = ConnectionManager()


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """Stream log file in real-time."""
    # Check auth via query param if password set
    if _config["password"]:
        token = websocket.query_params.get("token")
        if not token or not secrets.compare_digest(token, _config["password"]):
            await websocket.close(code=4001)
            return

    arche_dir = get_arche_dir()
    log_file = arche_dir / LOG

    await manager.connect(websocket, "logs")
    try:
        # Send existing log content
        if log_file.exists():
            content = log_file.read_text()
            # Send last 500 lines on connect
            lines = content.split('\n')[-500:]
            await websocket.send_json({"type": "init", "content": '\n'.join(lines)})

        # Stream new content
        last_size = log_file.stat().st_size if log_file.exists() else 0

        while True:
            try:
                # Check for new content
                if log_file.exists():
                    current_size = log_file.stat().st_size
                    if current_size > last_size:
                        with open(log_file, 'r') as f:
                            f.seek(last_size)
                            new_content = f.read()
                            if new_content:
                                await websocket.send_json({"type": "append", "content": new_content})
                        last_size = current_size
                    elif current_size < last_size:
                        # File was truncated/rotated
                        content = log_file.read_text()
                        await websocket.send_json({"type": "init", "content": content})
                        last_size = current_size

                # Check connection with ping
                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(0.5)

            except WebSocketDisconnect:
                break
    finally:
        manager.disconnect(websocket, "logs")


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """Stream agent events (status changes, tool calls)."""
    if _config["password"]:
        token = websocket.query_params.get("token")
        if not token or not secrets.compare_digest(token, _config["password"]):
            await websocket.close(code=4001)
            return

    arche_dir = get_arche_dir()

    await manager.connect(websocket, "events")
    try:
        last_state = {}

        while True:
            try:
                # Check for state changes
                current_state = read_state(arche_dir)
                running, pid = is_running(arche_dir)

                if current_state != last_state:
                    await websocket.send_json({
                        "type": "state",
                        "running": running,
                        "pid": pid,
                        "turn": current_state.get("turn", 1),
                        "last_mode": current_state.get("last_mode"),
                    })
                    last_state = current_state.copy()

                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(1)

            except WebSocketDisconnect:
                break
    finally:
        manager.disconnect(websocket, "events")


# === Health Check ===

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# === Static Files (for production build) ===

# Mount static files if frontend/dist exists
_frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA - fallback to index.html."""
        from fastapi.responses import FileResponse
        index = _frontend_dist / "index.html"
        file_path = _frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(index)
