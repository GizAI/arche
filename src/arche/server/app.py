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
)

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

# Set up session manager broadcast callback
session_manager.set_broadcast_callback(manager.broadcast_to_session)


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
        resume=req.resume,  # Pass resume session ID
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

                # Handle client messages
                msg_type = data.get("type")

                if msg_type == "send_message":
                    content = data.get("content", "")
                    system_prompt = data.get("system_prompt")
                    if content:
                        await session_manager.send_message(
                            session_id, content, system_prompt
                        )

                elif msg_type == "interrupt":
                    await session_manager.interrupt_session(session_id)

                elif msg_type == "permission_response":
                    await session_manager.respond_to_permission(
                        session_id,
                        data.get("request_id", ""),
                        data.get("allow", False),
                        modified_input=data.get("modified_input"),
                        reason=data.get("reason"),
                    )

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

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
