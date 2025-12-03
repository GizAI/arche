"""Arche FastAPI Server - Web UI backend.

Architecture: Imports utilities from arche.cli - no code duplication.
"""

import asyncio
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from arche.server.interactive import (
    session_manager,
    SessionState,
    list_existing_sessions,
    get_available_models,
    get_default_model,
    THINKING_BUDGETS,
)
from arche.server.background_tasks import background_task_manager, TaskStatus
from arche.server.checkpoints import checkpoint_manager
from arche.server.mcp_manager import mcp_server_manager, MCPServerConfig, MCPServerType
from arche.server.custom_commands import command_manager
from arche.server.hooks import hooks_manager, HookConfig, HookType
from arche.server.commands import handle_websocket_message, CommandContext
from arche.server.oauth_api import get_usage, get_profile

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
    "_initialized": False,
    "production": os.getenv("ARCHE_ENV", "development") == "production",
}

# Session management
SESSION_COOKIE = "arche_session"
SESSION_EXPIRY_HOURS = 24
_sessions: dict[str, datetime] = {}  # token -> expiry

# Rate limiting store: IP -> [(timestamp, endpoint), ...]
_rate_limit_store: dict[str, list[tuple[datetime, str]]] = defaultdict(list)


@app.on_event("startup")
async def startup_auto_init():
    """Auto-initialize server config from environment if not already done."""
    if not _config["_initialized"]:
        # Try to auto-detect project path from current working directory
        cwd = Path.cwd()
        arche_dir = cwd / ".arche"
        if arche_dir.exists():
            setup_server(cwd)

    # Initialize extended managers if config is ready
    if _config["_initialized"] and _config["arche_dir"]:
        arche_dir = _config["arche_dir"]
        project_path = _config["project_path"]

        # Update config directories for managers
        hooks_manager.config_dir = arche_dir
        checkpoint_manager.working_dir = project_path
        checkpoint_manager._checkpoint_file = arche_dir / "checkpoints.json"
        mcp_server_manager.config_dir = arche_dir

        # Load saved hooks from config
        await hooks_manager.load_config()

        # Load saved checkpoints
        await checkpoint_manager.load_checkpoints()

        # Load custom commands
        command_manager.load_commands(project_path)

        # Load saved MCP server configs and try to reconnect
        await mcp_server_manager.load_from_config()


def setup_server(project_path: Path, password: str | None = None):
    """Configure server with project path and optional auth."""
    _config["project_path"] = project_path
    _config["arche_dir"] = project_path / ".arche"

    # Ensure .arche dir exists
    init_arche_dir(_config["arche_dir"])

    # Read password from state.json if not provided via CLI
    if not password:
        state = read_state(_config["arche_dir"])
        server_config = state.get("server", {})
        password = server_config.get("password")

    _config["password"] = password
    _config["_initialized"] = True


def get_arche_dir() -> Path:
    """Get configured .arche directory."""
    if not _config["arche_dir"]:
        raise HTTPException(500, "Server not configured")
    return _config["arche_dir"]


def create_session() -> str:
    """Create new session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = datetime.now() + timedelta(hours=SESSION_EXPIRY_HOURS)
    return token


def verify_session(token: str | None) -> bool:
    """Check if session token is valid."""
    if not _config["password"]:
        return True
    if not token:
        return False
    expiry = _sessions.get(token)
    if not expiry or datetime.now() > expiry:
        _sessions.pop(token, None)
        return False
    return True


def get_session_token(request: Request) -> str | None:
    """Extract session token from cookie."""
    return request.cookies.get(SESSION_COOKIE)


async def require_auth(request: Request) -> bool:
    """Dependency: require valid session."""
    if not _config["password"]:
        return True
    if verify_session(get_session_token(request)):
        return True
    raise HTTPException(401, "Authentication required")


def rate_limit(request: Request, max_requests: int = 10, window_seconds: int = 60):
    """Simple rate limiting per IP address."""
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now()
    endpoint = request.url.path

    # Clean old entries outside window
    cutoff = now - timedelta(seconds=window_seconds)
    _rate_limit_store[client_ip] = [
        (ts, ep) for ts, ep in _rate_limit_store[client_ip] if ts > cutoff
    ]

    # Check rate limit
    recent_requests = [ep for ts, ep in _rate_limit_store[client_ip] if ep == endpoint]
    if len(recent_requests) >= max_requests:
        raise HTTPException(429, "Too many requests. Please try again later.")

    # Record this request
    _rate_limit_store[client_ip].append((now, endpoint))


# CORS middleware - Environment-based configuration
_allowed_origins = ["*"]  # Default for development
if _config["production"]:
    # In production, restrict to specific origins from environment
    # Example: ARCHE_CORS_ORIGINS="http://localhost:8420,https://arche.example.com"
    cors_origins = os.getenv("ARCHE_CORS_ORIGINS", "")
    if cors_origins:
        _allowed_origins = [origin.strip() for origin in cors_origins.split(",")]
    else:
        # If no origins specified in production, default to localhost only
        _allowed_origins = ["http://localhost:8420", "http://127.0.0.1:8420"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Only add security headers in production or if explicitly enabled
    if _config["production"] or os.getenv("ARCHE_SECURITY_HEADERS", "false").lower() == "true":
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Add CSP for production (less strict in dev for easier debugging)
        if _config["production"]:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data: https://fonts.googleapis.com https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none';"
            )

    return response


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


class SetupPasswordRequest(BaseModel):
    password: str | None = None  # None means skip setup


# === API Routes ===

@app.get("/api/setup/status")
async def get_setup_status():
    """Check if initial setup is needed."""
    # This endpoint must work before setup_server is called
    if not _config.get("arche_dir"):
        raise HTTPException(500, "Server not configured")

    arche_dir = get_arche_dir()
    state = read_state(arche_dir)
    server_config = state.get("server", {})

    # Setup is needed if no password is configured (neither in state nor via CLI)
    needs_setup = not _config.get("password") and not server_config.get("password")

    return {
        "needs_setup": needs_setup,
        "password_configured": bool(_config.get("password") or server_config.get("password")),
    }


@app.post("/api/setup/password")
async def setup_password(req: SetupPasswordRequest, request: Request = None):
    """Set password on first-time setup (no auth required)."""
    # Rate limit: 5 attempts per 5 minutes per IP
    if request:
        rate_limit(request, max_requests=5, window_seconds=300)

    arche_dir = get_arche_dir()
    state = read_state(arche_dir)
    server_config = state.get("server", {})

    # Only allow if setup is needed
    if _config["password"] or server_config.get("password"):
        raise HTTPException(403, "Password already configured")

    # Update state
    server_config["password"] = req.password
    server_config["setup_completed"] = True
    state["server"] = server_config
    write_state(arche_dir, state)

    # Update runtime config
    if req.password:
        _config["password"] = req.password

    return {"status": "configured", "password_set": bool(req.password)}


class LoginRequest(BaseModel):
    password: str


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    """Login and set session cookie."""
    rate_limit(request, max_requests=5, window_seconds=300)

    if _config["password"] and not secrets.compare_digest(req.password, _config["password"]):
        raise HTTPException(401, "Invalid password")

    token = create_session()
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=_config["production"],
        samesite="lax",
        max_age=SESSION_EXPIRY_HOURS * 3600,
    )
    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Clear session cookie."""
    token = get_session_token(request)
    _sessions.pop(token, None)
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/auth/check")
async def check_auth(request: Request):
    """Check if authenticated."""
    return {"authenticated": verify_session(get_session_token(request))}


@app.get("/api/status", response_model=StatusResponse)
async def get_status(auth: bool = Depends(require_auth)):
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
async def start_agent(req: StartRequest, auth: bool = Depends(require_auth)):
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
async def stop_agent(auth: bool = Depends(require_auth)):
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
    auth: bool = Depends(require_auth),
):
    """Resume a stopped agent."""
    arche_dir = get_arche_dir()
    running, pid = is_running(arche_dir)

    if running:
        raise HTTPException(409, f"Agent already running (PID {pid})")

    state = read_state(arche_dir)
    turn = state.get("turn", 1)

    # Auto-enable review mode if there's pending feedback
    if read_feedback(arche_dir)[0]:
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
        f.write(f"\n\033[33m{'━'*50}\033[0m\n\033[1;33m▷ Resumed\033[0m \033[2mTurn {turn}{mode_str} • {datetime.now().strftime('%H:%M:%S')}\033[0m\n\033[33m{'━'*50}\033[0m\n")

    start_daemon(arche_dir)
    return {"status": "resumed", "turn": turn}


@app.post("/api/pause")
async def pause_agent(auth: bool = Depends(require_auth)):
    """Pause agent after current turn."""
    arche_dir = get_arche_dir()
    running, _ = is_running(arche_dir)

    if not running:
        raise HTTPException(409, "Agent not running")

    (arche_dir / "paused").touch()
    return {"status": "paused"}


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest, auth: bool = Depends(require_auth)):
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
async def list_files(auth: bool = Depends(require_auth)):
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


def validate_file_path(path: str, arche_dir: Path, allow_write: bool = False) -> Path:
    """Validate file path is within .arche directory and safe to access.

    Args:
        path: Relative path from arche_dir
        arche_dir: Base .arche directory
        allow_write: If True, allow parent directory creation

    Returns:
        Resolved absolute path

    Raises:
        HTTPException: If path is invalid or outside arche_dir
    """
    # Block path traversal attempts
    if ".." in path or path.startswith("/"):
        raise HTTPException(403, "Invalid path: path traversal not allowed")

    # Block hidden files/directories (except .arche itself)
    parts = Path(path).parts
    if any(part.startswith(".") and part != ".arche" for part in parts):
        raise HTTPException(403, "Invalid path: hidden files not allowed")

    # Resolve full path
    try:
        file_path = (arche_dir / path).resolve()
        arche_dir_resolved = arche_dir.resolve()
    except Exception:
        raise HTTPException(403, "Invalid path format")

    # Ensure path stays within .arche
    if not str(file_path).startswith(str(arche_dir_resolved)):
        raise HTTPException(403, "Access denied: path outside allowed directory")

    # Additional checks for write operations
    if allow_write:
        # Block writing to sensitive files
        sensitive_patterns = ["state.json", "daemon.pid"]
        if any(pattern in str(file_path) for pattern in sensitive_patterns):
            raise HTTPException(403, "Access denied: cannot modify system files")

    return file_path


@app.get("/api/files/{path:path}")
async def read_file(path: str, auth: bool = Depends(require_auth)):
    """Read file content from .arche directory."""
    arche_dir = get_arche_dir()
    file_path = validate_file_path(path, arche_dir, allow_write=False)

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
async def write_file(path: str, file: FileContent, auth: bool = Depends(require_auth)):
    """Write file content to .arche directory."""
    arche_dir = get_arche_dir()
    file_path = validate_file_path(path, arche_dir, allow_write=True)

    # Create parent dirs if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(file.content)

    return {"status": "saved", "path": path}


# === WebSocket Endpoints ===

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {"logs": [], "events": []}
        # Interactive session connections: session_id -> list of websockets
        self.interactive_connections: dict[str, list[WebSocket]] = {}

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

    async def connect_interactive(self, websocket: WebSocket, session_id: str):
        """Connect to an interactive session."""
        await websocket.accept()
        if session_id not in self.interactive_connections:
            self.interactive_connections[session_id] = []
        self.interactive_connections[session_id].append(websocket)

    def disconnect_interactive(self, websocket: WebSocket, session_id: str):
        """Disconnect from an interactive session."""
        if session_id in self.interactive_connections:
            if websocket in self.interactive_connections[session_id]:
                self.interactive_connections[session_id].remove(websocket)
            if not self.interactive_connections[session_id]:
                del self.interactive_connections[session_id]

    async def broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast message to all clients of an interactive session."""
        if session_id not in self.interactive_connections:
            return
        disconnected = []
        for ws in self.interactive_connections[session_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_interactive(ws, session_id)

    async def broadcast_to_all_interactive(self, message: dict):
        """Broadcast message to all interactive clients."""
        for session_id in list(self.interactive_connections.keys()):
            await self.broadcast_to_session(session_id, message)


manager = ConnectionManager()

# Set up broadcast callbacks for all managers
session_manager.set_broadcast_callback(manager.broadcast_to_session)
background_task_manager.set_broadcast_callback(manager.broadcast_to_session)
checkpoint_manager.set_broadcast_callback(manager.broadcast_to_session)
mcp_server_manager.set_broadcast_callback(manager.broadcast_to_session)
hooks_manager.set_broadcast_callback(manager.broadcast_to_session)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """Stream log file in real-time."""
    # Check auth via cookie
    if not verify_session(websocket.cookies.get(SESSION_COOKIE)):
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
    if not verify_session(websocket.cookies.get(SESSION_COOKIE)):
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


# === Interactive Mode API ===

class CreateSessionRequest(BaseModel):
    name: str | None = None
    model: str | None = None
    cwd: str | None = None
    permission_mode: str = "default"
    resume: str | None = None  # Session ID to resume from Claude CLI
    engine: str = "claude_sdk"  # claude_sdk | deepagents
    capabilities: list[str] | None = None  # DeepAgents capabilities


class SendMessageRequest(BaseModel):
    content: str
    system_prompt: str | None = None


class PermissionResponseRequest(BaseModel):
    request_id: str
    allow: bool
    modified_input: dict | None = None
    reason: str | None = None


class UpdateSessionRequest(BaseModel):
    name: str | None = None
    model: str | None = None
    permission_mode: str | None = None
    engine: str | None = None
    capabilities: list[str] | None = None


class TodoRequest(BaseModel):
    content: str
    priority: int = 0


class TodoStatusRequest(BaseModel):
    status: str  # pending, in_progress, completed


@app.get("/api/interactive/sessions")
async def list_interactive_sessions(auth: bool = Depends(require_auth)):
    """List all interactive sessions (both active and existing/resumable)."""
    # Get active sessions from session manager
    active_sessions = session_manager.list_sessions()

    # Get existing Claude CLI sessions that can be resumed
    arche_dir = get_arche_dir()
    project_root = arche_dir.parent
    existing_sessions = list_existing_sessions(cwd=project_root, limit=30)

    return {
        "sessions": active_sessions,
        "existing_sessions": [s.to_dict() for s in existing_sessions],
    }


@app.get("/api/interactive/existing-sessions")
async def get_existing_sessions(
    project_only: bool = True,
    limit: int = 50,
    auth: bool = Depends(require_auth),
):
    """List existing Claude CLI sessions that can be resumed."""
    arche_dir = get_arche_dir()
    cwd = arche_dir.parent if project_only else None
    existing = list_existing_sessions(cwd=cwd, limit=limit)
    return {"sessions": [s.to_dict() for s in existing]}


@app.get("/api/interactive/models")
async def get_models(auth: bool = Depends(require_auth)):
    """Get list of available Claude models."""
    models = get_available_models()
    default = get_default_model()
    return {
        "models": models,
        "default": default,
    }


@app.post("/api/interactive/sessions")
async def create_interactive_session(
    req: CreateSessionRequest,
    auth: bool = Depends(require_auth),
):
    """Create a new interactive session or resume an existing one."""
    arche_dir = get_arche_dir()

    # Use project root as default cwd
    cwd = req.cwd or str(arche_dir.parent)

    # Use default model if not specified
    model = req.model or get_default_model()

    session = await session_manager.create_session(
        name=req.name,
        model=model,
        cwd=cwd,
        permission_mode=req.permission_mode,
        resume=req.resume,
        engine=req.engine,
        capabilities=req.capabilities,
    )
    return {"session": session.to_dict()}


@app.get("/api/interactive/sessions/{session_id}")
async def get_interactive_session(
    session_id: str,
    include_messages: bool = False,
    auth: bool = Depends(require_auth),
):
    """Get session details."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"session": session.to_dict(include_messages=include_messages)}


@app.patch("/api/interactive/sessions/{session_id}")
async def update_interactive_session(
    session_id: str,
    req: UpdateSessionRequest,
    auth: bool = Depends(require_auth),
):
    """Update session settings."""
    session = await session_manager.update_session(
        session_id,
        name=req.name,
        model=req.model,
        permission_mode=req.permission_mode,
    )
    if not session:
        raise HTTPException(404, "Session not found")
    return {"session": session.to_dict()}


@app.delete("/api/interactive/sessions/{session_id}")
async def delete_interactive_session(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Delete a session."""
    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(404, "Session not found")
    return {"status": "deleted"}


@app.post("/api/interactive/sessions/{session_id}/messages")
async def send_interactive_message(
    session_id: str,
    req: SendMessageRequest,
    auth: bool = Depends(require_auth),
):
    """Send a message to the session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if session.state not in (SessionState.IDLE, SessionState.COMPLETED, SessionState.ERROR):
        raise HTTPException(409, f"Session is busy (state: {session.state.value})")

    success = await session_manager.send_message(
        session_id,
        req.content,
        system_prompt=req.system_prompt,
    )

    if not success:
        raise HTTPException(500, "Failed to send message")

    return {"status": "sent"}


@app.post("/api/interactive/sessions/{session_id}/interrupt")
async def interrupt_interactive_session(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Interrupt a running session."""
    success = await session_manager.interrupt_session(session_id)
    if not success:
        raise HTTPException(409, "Session not running or not found")
    return {"status": "interrupted"}


@app.post("/api/interactive/sessions/{session_id}/permission")
async def respond_to_permission(
    session_id: str,
    req: PermissionResponseRequest,
    auth: bool = Depends(require_auth),
):
    """Respond to a permission request."""
    success = await session_manager.respond_to_permission(
        session_id,
        req.request_id,
        req.allow,
        modified_input=req.modified_input,
        reason=req.reason,
    )
    if not success:
        raise HTTPException(404, "Permission request not found or expired")
    return {"status": "responded", "allowed": req.allow}


@app.get("/api/interactive/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get all messages in a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"messages": [m.to_dict() for m in session.messages]}


# === DeepAgents Specific Endpoints ===

@app.get("/api/interactive/sessions/{session_id}/todos")
async def get_session_todos(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get todo list for a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"todos": [t.to_dict() for t in session.todos]}


@app.post("/api/interactive/sessions/{session_id}/todos")
async def add_session_todo(
    session_id: str,
    req: TodoRequest,
    auth: bool = Depends(require_auth),
):
    """Add a new todo item."""
    todo = await session_manager.add_todo(session_id, req.content, req.priority)
    if not todo:
        raise HTTPException(404, "Session not found")
    return {"todo": todo.to_dict()}


@app.patch("/api/interactive/sessions/{session_id}/todos/{todo_id}")
async def update_session_todo(
    session_id: str,
    todo_id: str,
    req: TodoStatusRequest,
    auth: bool = Depends(require_auth),
):
    """Update a todo item's status."""
    success = await session_manager.update_todo_status(session_id, todo_id, req.status)
    if not success:
        raise HTTPException(404, "Session or todo not found")
    return {"status": "updated"}


@app.delete("/api/interactive/sessions/{session_id}/todos/{todo_id}")
async def delete_session_todo(
    session_id: str,
    todo_id: str,
    auth: bool = Depends(require_auth),
):
    """Delete a todo item."""
    success = await session_manager.delete_todo(session_id, todo_id)
    if not success:
        raise HTTPException(404, "Session or todo not found")
    return {"status": "deleted"}


@app.get("/api/interactive/sessions/{session_id}/file-operations")
async def get_session_file_operations(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get file operations for a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"file_operations": [f.to_dict() for f in session.file_operations]}


@app.get("/api/interactive/skills")
async def list_available_skills(auth: bool = Depends(require_auth)):
    """List available skills."""
    arche_dir = get_arche_dir()
    skills_dir = arche_dir / "skills"
    skills = []

    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_yaml = skill_dir / "skill.yaml"
                if skill_yaml.exists():
                    try:
                        import yaml
                        with open(skill_yaml) as f:
                            data = yaml.safe_load(f)
                        skills.append({
                            "name": skill_dir.name,
                            "description": data.get("description", ""),
                        })
                    except Exception:
                        skills.append({
                            "name": skill_dir.name,
                            "description": "",
                        })

    return {"skills": skills}


@app.post("/api/interactive/sessions/{session_id}/skills/{skill_name}")
async def load_skill(
    session_id: str,
    skill_name: str,
    auth: bool = Depends(require_auth),
):
    """Load a skill into a session."""
    success = await session_manager.load_skill(session_id, skill_name)
    if not success:
        raise HTTPException(404, "Session or skill not found")
    return {"status": "loaded"}


@app.delete("/api/interactive/sessions/{session_id}/skills/{skill_name}")
async def unload_skill(
    session_id: str,
    skill_name: str,
    auth: bool = Depends(require_auth),
):
    """Unload a skill from a session."""
    success = await session_manager.unload_skill(session_id, skill_name)
    if not success:
        raise HTTPException(404, "Session not found or skill not loaded")
    return {"status": "unloaded"}


@app.post("/api/interactive/sessions/{session_id}/engine")
async def set_session_engine(
    session_id: str,
    engine: str,
    auth: bool = Depends(require_auth),
):
    """Change the engine for a session."""
    success = await session_manager.set_engine(session_id, engine)
    if not success:
        raise HTTPException(400, "Invalid engine or session not found")
    return {"status": "updated", "engine": engine}


@app.post("/api/interactive/sessions/{session_id}/capabilities")
async def set_session_capabilities(
    session_id: str,
    capabilities: list[str],
    auth: bool = Depends(require_auth),
):
    """Update session capabilities."""
    success = await session_manager.set_capabilities(session_id, capabilities)
    if not success:
        raise HTTPException(404, "Session not found")
    return {"status": "updated", "capabilities": capabilities}


@app.get("/api/interactive/sessions/{session_id}/usage")
async def get_session_usage(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get token usage for a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "input_tokens": session.input_tokens,
        "output_tokens": session.output_tokens,
        "total_cost_usd": session.total_cost_usd,
    }


# --- File Operations Approval ---

class FileOpRejectRequest(BaseModel):
    reason: str | None = None


@app.post("/api/interactive/sessions/{session_id}/file-operations/{op_id}/approve")
async def approve_file_operation(
    session_id: str,
    op_id: str,
    auth: bool = Depends(require_auth),
):
    """Approve a pending file operation."""
    success = await session_manager.approve_file_operation(session_id, op_id)
    if not success:
        raise HTTPException(404, "Session or operation not found")
    return {"status": "approved"}


@app.post("/api/interactive/sessions/{session_id}/file-operations/{op_id}/reject")
async def reject_file_operation(
    session_id: str,
    op_id: str,
    req: FileOpRejectRequest = FileOpRejectRequest(),
    auth: bool = Depends(require_auth),
):
    """Reject a pending file operation."""
    success = await session_manager.reject_file_operation(session_id, op_id, req.reason)
    if not success:
        raise HTTPException(404, "Session or operation not found")
    return {"status": "rejected"}


# === Extended Claude Code Features ===

class ThinkingModeRequest(BaseModel):
    mode: str  # normal, think, think_hard, ultrathink


class PlanModeRequest(BaseModel):
    enabled: bool


class BudgetRequest(BaseModel):
    budget_usd: float | None


class BackgroundTaskRequest(BaseModel):
    command: str
    timeout: float | None = None


class CheckpointRequest(BaseModel):
    name: str
    description: str | None = None


class MCPServerRequest(BaseModel):
    name: str
    type: str  # stdio, sse, http
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | None = None
    headers: dict[str, str] = {}


class HookRequest(BaseModel):
    id: str | None = None  # Auto-generated if not provided
    name: str | None = None  # Auto-generated if not provided
    type: str  # pre_tool_use, post_tool_use, user_prompt_submit, stop
    enabled: bool = True
    matcher: str | None = None
    command: str | None = None
    timeout: float = 30.0


# --- Thinking Mode ---

@app.get("/api/interactive/sessions/{session_id}/thinking-mode")
async def get_thinking_mode(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get current thinking mode for session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "mode": session.thinking_mode,
        "available_modes": list(THINKING_BUDGETS.keys()),
    }


@app.post("/api/interactive/sessions/{session_id}/thinking-mode")
async def set_thinking_mode(
    session_id: str,
    req: ThinkingModeRequest,
    auth: bool = Depends(require_auth),
):
    """Set thinking mode for session."""
    success = await session_manager.set_thinking_mode(session_id, req.mode)
    if not success:
        raise HTTPException(400, "Invalid mode or session not found")
    return {"status": "updated", "mode": req.mode}


# --- Plan Mode ---

@app.get("/api/interactive/sessions/{session_id}/plan-mode")
async def get_plan_mode(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get plan mode status for session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {
        "enabled": session.plan_mode_active,
        "proposed_plan": session.proposed_plan,
    }


@app.post("/api/interactive/sessions/{session_id}/plan-mode")
async def set_plan_mode(
    session_id: str,
    req: PlanModeRequest,
    auth: bool = Depends(require_auth),
):
    """Enable/disable plan mode for session."""
    success = await session_manager.set_plan_mode(session_id, req.enabled)
    if not success:
        raise HTTPException(404, "Session not found")
    return {"status": "updated", "enabled": req.enabled}


@app.post("/api/interactive/sessions/{session_id}/approve-plan")
async def approve_plan(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Approve the proposed plan and exit plan mode."""
    success = await session_manager.approve_plan(session_id)
    if not success:
        raise HTTPException(400, "No plan to approve or session not found")
    return {"status": "approved"}


# --- Mode Approval ---

class ApprovalResponseRequest(BaseModel):
    """Request to respond to a mode approval."""
    decision: str  # approve, modify, reject
    feedback: str | None = None
    modified_result: dict | None = None


@app.get("/api/interactive/sessions/{session_id}/approval")
async def get_approval_status(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """Get pending approval request if any."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "has_pending": session.pending_approval is not None,
        "approval": session.pending_approval,
    }


@app.post("/api/interactive/sessions/{session_id}/approval")
async def respond_to_approval(
    session_id: str,
    req: ApprovalResponseRequest,
    auth: bool = Depends(require_auth),
):
    """Respond to a pending approval request."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if not session.pending_approval:
        raise HTTPException(400, "No pending approval")

    # Write response file (daemon reads it)
    from pathlib import Path
    arche_dir = Path(session.cwd) / ".arche"
    response = {"action": req.decision}
    if req.feedback:
        response["feedback"] = req.feedback
    if req.modified_result:
        response["modified_result"] = req.modified_result

    (arche_dir / "approval_response.json").write_text(json.dumps(response))

    # Clear pending
    session.pending_approval = None
    session.state = SessionState.IDLE

    await session_manager._broadcast_to_session(session_id, {
        "type": "approval_response",
        "decision": req.decision,
    })

    return {"status": "responded", "decision": req.decision}


# --- Budget Control ---

@app.post("/api/interactive/sessions/{session_id}/budget")
async def set_budget(
    session_id: str,
    req: BudgetRequest,
    auth: bool = Depends(require_auth),
):
    """Set budget limit for session."""
    success = await session_manager.set_budget(session_id, req.budget_usd)
    if not success:
        raise HTTPException(404, "Session not found")
    return {"status": "updated", "budget_usd": req.budget_usd}


# --- Background Tasks ---

@app.get("/api/interactive/sessions/{session_id}/background-tasks")
async def list_background_tasks(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """List background tasks for session."""
    tasks = background_task_manager.list_tasks(session_id)
    return {"tasks": [t.to_dict() for t in tasks]}


@app.post("/api/interactive/sessions/{session_id}/background-tasks")
async def create_background_task(
    session_id: str,
    req: BackgroundTaskRequest,
    auth: bool = Depends(require_auth),
):
    """Start a background task."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    task = await background_task_manager.start_task(
        session_id=session_id,
        command=req.command,
        cwd=session.cwd,
        timeout=req.timeout,
    )
    return {"task": task.to_dict()}


@app.get("/api/interactive/sessions/{session_id}/background-tasks/{task_id}")
async def get_background_task(
    session_id: str,
    task_id: str,
    auth: bool = Depends(require_auth),
):
    """Get background task details."""
    task = background_task_manager.get_task(task_id)
    if not task or task.session_id != session_id:
        raise HTTPException(404, "Task not found")
    return {"task": task.to_dict()}


@app.get("/api/interactive/sessions/{session_id}/background-tasks/{task_id}/output")
async def get_background_task_output(
    session_id: str,
    task_id: str,
    since_line: int = 0,
    limit: int = 100,
    auth: bool = Depends(require_auth),
):
    """Get background task output."""
    task = background_task_manager.get_task(task_id)
    if not task or task.session_id != session_id:
        raise HTTPException(404, "Task not found")

    lines, has_more = background_task_manager.get_output(task_id, since_line, limit)
    return {
        "lines": lines,
        "has_more": has_more,
        "total_lines": len(task.output_lines),
    }


@app.delete("/api/interactive/sessions/{session_id}/background-tasks/{task_id}")
async def cancel_background_task(
    session_id: str,
    task_id: str,
    auth: bool = Depends(require_auth),
):
    """Cancel a background task."""
    task = background_task_manager.get_task(task_id)
    if not task or task.session_id != session_id:
        raise HTTPException(404, "Task not found")

    success = await background_task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(400, "Task cannot be cancelled")
    return {"status": "cancelled"}


# --- Checkpoints ---

@app.get("/api/interactive/sessions/{session_id}/checkpoints")
async def list_checkpoints(
    session_id: str,
    auth: bool = Depends(require_auth),
):
    """List checkpoints for session."""
    checkpoints = checkpoint_manager.list_checkpoints(session_id)
    return {"checkpoints": [c.to_dict() for c in checkpoints]}


@app.post("/api/interactive/sessions/{session_id}/checkpoints")
async def create_checkpoint(
    session_id: str,
    req: CheckpointRequest,
    auth: bool = Depends(require_auth),
):
    """Create a checkpoint."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    checkpoint = await checkpoint_manager.create_checkpoint(
        session_id=session_id,
        name=req.name,
        description=req.description,
        cwd=Path(session.cwd),
    )
    if not checkpoint:
        raise HTTPException(500, "Failed to create checkpoint (not a git repo?)")
    return {"checkpoint": checkpoint.to_dict()}


@app.post("/api/interactive/sessions/{session_id}/checkpoints/{checkpoint_id}/restore")
async def restore_checkpoint(
    session_id: str,
    checkpoint_id: str,
    auth: bool = Depends(require_auth),
):
    """Restore to a checkpoint."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    success = await checkpoint_manager.restore_checkpoint(
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        cwd=Path(session.cwd),
    )
    if not success:
        raise HTTPException(400, "Failed to restore checkpoint")
    return {"status": "restored"}


@app.delete("/api/interactive/sessions/{session_id}/checkpoints/{checkpoint_id}")
async def delete_checkpoint(
    session_id: str,
    checkpoint_id: str,
    auth: bool = Depends(require_auth),
):
    """Delete a checkpoint."""
    success = await checkpoint_manager.delete_checkpoint(checkpoint_id)
    if not success:
        raise HTTPException(404, "Checkpoint not found")
    return {"status": "deleted"}


# --- MCP Servers ---

@app.get("/api/mcp/servers")
async def list_mcp_servers(auth: bool = Depends(require_auth)):
    """List all MCP servers."""
    servers = mcp_server_manager.list_servers()
    return {"servers": [s.to_dict() for s in servers]}


@app.post("/api/mcp/servers")
async def add_mcp_server(
    req: MCPServerRequest,
    auth: bool = Depends(require_auth),
):
    """Add and connect to an MCP server."""
    try:
        config = MCPServerConfig(
            name=req.name,
            type=MCPServerType(req.type),
            command=req.command,
            args=req.args,
            env=req.env,
            url=req.url,
            headers=req.headers,
        )
        server = await mcp_server_manager.add_server(config)
        return {"server": server.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/mcp/servers/{name}")
async def get_mcp_server(
    name: str,
    auth: bool = Depends(require_auth),
):
    """Get MCP server details."""
    server = mcp_server_manager.get_server(name)
    if not server:
        raise HTTPException(404, "Server not found")
    return {"server": server.to_dict()}


@app.get("/api/mcp/servers/{name}/tools")
async def get_mcp_server_tools(
    name: str,
    auth: bool = Depends(require_auth),
):
    """Get tools from an MCP server."""
    server = mcp_server_manager.get_server(name)
    if not server:
        raise HTTPException(404, "Server not found")
    return {"tools": [t.to_dict() for t in server.tools]}


@app.delete("/api/mcp/servers/{name}")
async def remove_mcp_server(
    name: str,
    auth: bool = Depends(require_auth),
):
    """Remove an MCP server."""
    success = await mcp_server_manager.remove_server(name)
    if not success:
        raise HTTPException(404, "Server not found")
    return {"status": "removed"}


@app.get("/api/mcp/tools")
async def list_all_mcp_tools(auth: bool = Depends(require_auth)):
    """Get all tools from all connected MCP servers."""
    tools = mcp_server_manager.get_all_tools()
    return {"tools": tools}


# --- Custom Commands ---

@app.get("/api/commands")
async def list_commands(auth: bool = Depends(require_auth)):
    """List all available commands (built-in + custom)."""
    arche_dir = get_arche_dir()
    command_manager.load_commands(arche_dir.parent)
    commands = command_manager.list_commands()
    return {"commands": commands}


@app.post("/api/commands/{name}/execute")
async def execute_command(
    name: str,
    args: list[str] | None = None,
    kwargs: dict[str, str] | None = None,
    auth: bool = Depends(require_auth),
):
    """Execute a custom command."""
    try:
        prompt, metadata = command_manager.execute_command(name, args, kwargs)
        return {
            "prompt": prompt,
            "metadata": metadata,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/commands/reload")
async def reload_commands(auth: bool = Depends(require_auth)):
    """Reload custom commands from disk."""
    arche_dir = get_arche_dir()
    count = command_manager.load_commands(arche_dir.parent)
    return {"status": "reloaded", "count": count}


# --- Hooks ---

@app.get("/api/hooks")
async def list_hooks(
    type: str | None = None,
    auth: bool = Depends(require_auth),
):
    """List all hooks."""
    hook_type = HookType(type) if type else None
    hooks = hooks_manager.list_hooks(hook_type)
    return {"hooks": [h.to_dict() for h in hooks]}


@app.post("/api/hooks")
async def register_hook(
    req: HookRequest,
    auth: bool = Depends(require_auth),
):
    """Register a new hook."""
    try:
        # Auto-generate id and name if not provided
        hook_id = req.id or secrets.token_hex(4)
        hook_name = req.name or f"{req.type}-hook-{hook_id[:8]}"

        config = HookConfig(
            id=hook_id,
            name=hook_name,
            type=HookType(req.type),
            enabled=req.enabled,
            matcher=req.matcher,
            command=req.command,
            timeout=req.timeout,
        )
        hook = hooks_manager.register_hook(config)
        return {"hook": hook.to_dict()}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/hooks/{hook_id}")
async def get_hook(
    hook_id: str,
    auth: bool = Depends(require_auth),
):
    """Get hook details."""
    hook = hooks_manager.get_hook(hook_id)
    if not hook:
        raise HTTPException(404, "Hook not found")
    return {"hook": hook.to_dict()}


@app.patch("/api/hooks/{hook_id}")
async def update_hook(
    hook_id: str,
    enabled: bool,
    auth: bool = Depends(require_auth),
):
    """Enable/disable a hook."""
    success = hooks_manager.set_hook_enabled(hook_id, enabled)
    if not success:
        raise HTTPException(404, "Hook not found")
    return {"status": "updated", "enabled": enabled}


@app.delete("/api/hooks/{hook_id}")
async def unregister_hook(
    hook_id: str,
    auth: bool = Depends(require_auth),
):
    """Unregister a hook."""
    success = hooks_manager.unregister_hook(hook_id)
    if not success:
        raise HTTPException(404, "Hook not found")
    return {"status": "unregistered"}


# --- OAuth API (Usage & Profile) ---

@app.get("/api/usage")
async def get_api_usage(auth: bool = Depends(require_auth)):
    """Get API usage information."""
    usage = get_usage()
    if not usage:
        return {"error": "Unable to fetch usage (check credentials)"}
    return {"usage": usage.to_dict()}


@app.get("/api/profile")
async def get_api_profile(auth: bool = Depends(require_auth)):
    """Get user profile information."""
    profile = get_profile()
    if not profile:
        return {"error": "Unable to fetch profile (check credentials)"}
    return {"profile": profile.to_dict()}


@app.websocket("/ws/interactive/{session_id}")
async def websocket_interactive(websocket: WebSocket, session_id: str):
    """WebSocket for real-time interactive session updates."""
    # Check auth via cookie
    if not verify_session(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4001)
        return

    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004)
        return

    await manager.connect_interactive(websocket, session_id)
    try:
        # Send current session state
        await websocket.send_json({
            "type": "session_state",
            "session": session.to_dict(include_messages=True),
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)

                # Handle client messages using Command pattern
                msg_type = data.get("type")
                if msg_type:
                    # Create command context with all managers
                    cmd_context = CommandContext(
                        session_manager=session_manager,
                        background_task_manager=background_task_manager,
                        checkpoint_manager=checkpoint_manager,
                        mcp_server_manager=mcp_server_manager,
                        hooks_manager=hooks_manager,
                        websocket=websocket,
                    )
                    # Dispatch to registered command handler
                    await handle_websocket_message(msg_type, session_id, data, cmd_context)

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

            except WebSocketDisconnect:
                break

    except Exception:
        pass
    finally:
        manager.disconnect_interactive(websocket, session_id)


@app.websocket("/ws/interactive")
async def websocket_interactive_global(websocket: WebSocket):
    """WebSocket for global interactive session list updates."""
    if not verify_session(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        # Send current session list
        await websocket.send_json({
            "type": "sessions_list",
            "sessions": session_manager.list_sessions(),
        })

        # Monitor for changes
        last_sessions = session_manager.list_sessions()

        while True:
            try:
                # Check for new/changed sessions
                current_sessions = session_manager.list_sessions()
                if current_sessions != last_sessions:
                    await websocket.send_json({
                        "type": "sessions_list",
                        "sessions": current_sessions,
                    })
                    last_sessions = current_sessions

                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(1)

            except WebSocketDisconnect:
                break

    except Exception:
        pass


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
