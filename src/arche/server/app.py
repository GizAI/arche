"""Arche FastAPI Server - Full control & monitoring daemon."""

import asyncio
import hashlib
import json
import os
import re
import secrets
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from arche.engines import create_engine, EventType

# Constants
LOG = "arche.log"
PID = "arche.pid"
STATE = "state.json"
INFINITE = "infinite"
FORCE_REVIEW = "force_review"
FORCE_RETRO = "force_retro"
STEP_MODE = "step"
PROJECT_RULES = "PROJECT_RULES.md"

app = FastAPI(
    title="Arche Daemon",
    description="Long-lived coding agent with full control & monitoring",
    version="0.2.0",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBasic()


class ServerConfig:
    """Server runtime configuration."""
    def __init__(self):
        self.arche_dir: Path | None = None
        self.project_root: Path | None = None
        self.password_hash: str | None = None
        self.sessions: dict[str, datetime] = {}
        self.log_connections: list[WebSocket] = []
        self.engine_task: asyncio.Task | None = None
        self.current_engine = None


config = ServerConfig()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify password for HTTP Basic Auth."""
    if not config.password_hash:
        return True
    if hash_password(credentials.password) != config.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


# Pydantic models
class StartRequest(BaseModel):
    goal: str
    engine: str = "claude_sdk"
    model: Optional[str] = None
    plan: bool = False
    infinite: bool = False
    step: bool = False
    retro_every: str = "auto"


class FeedbackRequest(BaseModel):
    message: str
    priority: str = "medium"
    interrupt: bool = False


class StatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    turn: int = 1
    mode: str = "task"
    engine: str = "claude_sdk"
    goal: Optional[str] = None
    uptime: Optional[str] = None


# Helper functions
def read_state() -> dict:
    if not config.arche_dir:
        return {}
    state_file = config.arche_dir / STATE
    try:
        return json.loads(state_file.read_text()) if state_file.exists() else {}
    except:
        return {}


def write_state(state: dict):
    if config.arche_dir:
        (config.arche_dir / STATE).write_text(json.dumps(state, indent=2))


def is_running() -> tuple[bool, int | None]:
    if not config.arche_dir:
        return False, None
    pid_file = config.arche_dir / PID
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except:
        pid_file.unlink(missing_ok=True)
        return False, None


def kill_process(pid: int, force: bool = False):
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def get_log_content(lines: int = 500) -> str:
    if not config.arche_dir:
        return ""
    log_file = config.arche_dir / LOG
    if not log_file.exists():
        return ""
    content = log_file.read_text()
    log_lines = content.split('\n')
    return '\n'.join(log_lines[-lines:])


def list_journals() -> list[dict]:
    if not config.arche_dir:
        return []
    journal_dir = config.arche_dir / "journal"
    if not journal_dir.exists():
        return []
    journals = []
    for f in sorted(journal_dir.glob("*.yaml"), reverse=True):
        journals.append({
            "name": f.name,
            "path": str(f.relative_to(config.arche_dir)),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return journals


def list_plans() -> list[dict]:
    if not config.arche_dir:
        return []
    plan_dir = config.arche_dir / "plan"
    if not plan_dir.exists():
        return []
    plans = []
    for f in sorted(plan_dir.glob("*.yaml"), reverse=True):
        plans.append({
            "name": f.name,
            "path": str(f.relative_to(config.arche_dir)),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return plans


def list_feedbacks() -> list[dict]:
    if not config.arche_dir:
        return []
    fb_dir = config.arche_dir / "feedback"
    if not fb_dir.exists():
        return []
    feedbacks = []
    for subdir in ["pending", "reviewed"]:
        d = fb_dir / subdir
        if d.exists():
            for f in sorted(d.glob("*.yaml"), reverse=True):
                feedbacks.append({
                    "name": f.name,
                    "status": subdir,
                    "path": str(f.relative_to(config.arche_dir)),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
    return feedbacks


# API Endpoints
@app.get("/api/status", response_model=StatusResponse)
async def get_status(_: bool = Depends(verify_password)):
    running, pid = is_running()
    state = read_state()
    mode = "infinite" if config.arche_dir and (config.arche_dir / INFINITE).exists() else "task"
    if config.arche_dir and (config.arche_dir / STEP_MODE).exists():
        mode += " step"

    return StatusResponse(
        running=running,
        pid=pid,
        turn=state.get("turn", 1),
        mode=mode,
        engine=state.get("engine", {}).get("type", "claude_sdk"),
        goal=state.get("goal"),
    )


@app.post("/api/start")
async def start_agent(req: StartRequest, _: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")

    running, pid = is_running()
    if running:
        raise HTTPException(400, f"Already running (PID {pid}). Stop first.")

    # Setup directories
    config.arche_dir.mkdir(exist_ok=True)
    (config.arche_dir / "journal").mkdir(exist_ok=True)
    (config.arche_dir / "plan").mkdir(exist_ok=True)
    (config.arche_dir / "retrospective").mkdir(exist_ok=True)

    # Write state
    engine_kwargs = {"model": req.model} if req.model else {}
    state = {
        "engine": {"type": req.engine, "kwargs": engine_kwargs},
        "retro_every": req.retro_every,
        "turn": 1,
        "plan_mode": req.plan,
        "goal": req.goal,
    }
    write_state(state)

    # Flags
    if req.infinite:
        (config.arche_dir / INFINITE).touch()
    else:
        (config.arche_dir / INFINITE).unlink(missing_ok=True)
    if req.step:
        (config.arche_dir / STEP_MODE).touch()
    else:
        (config.arche_dir / STEP_MODE).unlink(missing_ok=True)

    # Clear log and start
    (config.arche_dir / LOG).write_text(f"Started: {datetime.now().isoformat()}\nGoal: {req.goal}\nEngine: {req.engine}\n")

    # Start engine in background
    config.engine_task = asyncio.create_task(run_agent_loop(req.goal))

    return {"status": "started", "goal": req.goal}


@app.post("/api/stop")
async def stop_agent(_: bool = Depends(verify_password)):
    running, pid = is_running()
    if not running:
        raise HTTPException(400, "Not running")

    # Cancel engine task if exists
    if config.engine_task:
        config.engine_task.cancel()
        config.engine_task = None

    # Cancel current engine
    if config.current_engine:
        await config.current_engine.cancel()

    kill_process(pid)

    for _ in range(10):
        await asyncio.sleep(0.5)
        if not is_running()[0]:
            return {"status": "stopped"}

    kill_process(pid, force=True)
    if config.arche_dir:
        (config.arche_dir / PID).unlink(missing_ok=True)
    return {"status": "killed"}


@app.post("/api/resume")
async def resume_agent(_: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")

    running, pid = is_running()
    if running:
        raise HTTPException(400, f"Already running (PID {pid})")

    (config.arche_dir / FORCE_REVIEW).touch()

    with open(config.arche_dir / LOG, "a") as f:
        f.write(f"\n{'='*50}\nResumed: {datetime.now().isoformat()}\n{'='*50}\n")

    state = read_state()
    goal = state.get("goal")
    config.engine_task = asyncio.create_task(run_agent_loop(goal))

    return {"status": "resumed"}


@app.post("/api/retro")
async def trigger_retro(_: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")

    running, pid = is_running()
    if running:
        if config.engine_task:
            config.engine_task.cancel()
        if config.current_engine:
            await config.current_engine.cancel()
        kill_process(pid)
        await asyncio.sleep(1)

    (config.arche_dir / FORCE_RETRO).touch()
    state = read_state()
    goal = state.get("goal")
    config.engine_task = asyncio.create_task(run_agent_loop(goal))

    return {"status": "retro started"}


@app.post("/api/feedback")
async def add_feedback(req: FeedbackRequest, _: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")

    feedback_dir = config.arche_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now()
    slug = re.sub(r'[^a-z0-9-]', '-', req.message[:30].lower())
    (feedback_dir / f"{ts:%Y%m%d-%H%M}-{slug}.yaml").write_text(
        f'meta:\n  timestamp: "{ts.isoformat()}"\nsummary: "{req.message}"\npriority: "{req.priority}"\n'
    )

    if req.interrupt:
        running, pid = is_running()
        if running:
            if config.engine_task:
                config.engine_task.cancel()
            if config.current_engine:
                await config.current_engine.cancel()
            kill_process(pid)
            await asyncio.sleep(1)

        (config.arche_dir / FORCE_REVIEW).touch()
        state = read_state()
        goal = state.get("goal")
        config.engine_task = asyncio.create_task(run_agent_loop(goal))

        return {"status": "feedback added and review started"}

    return {"status": "feedback added"}


@app.get("/api/logs")
async def get_logs(lines: int = 500, _: bool = Depends(verify_password)):
    return {"logs": get_log_content(lines)}


@app.get("/api/journals")
async def get_journals(_: bool = Depends(verify_password)):
    return {"journals": list_journals()}


@app.get("/api/journal/{name}")
async def get_journal(name: str, _: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")
    journal_file = config.arche_dir / "journal" / name
    if not journal_file.exists():
        raise HTTPException(404, "Journal not found")
    return {"content": journal_file.read_text()}


@app.get("/api/plans")
async def get_plans(_: bool = Depends(verify_password)):
    return {"plans": list_plans()}


@app.get("/api/plan/{name}")
async def get_plan(name: str, _: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")
    plan_file = config.arche_dir / "plan" / name
    if not plan_file.exists():
        raise HTTPException(404, "Plan not found")
    return {"content": plan_file.read_text()}


@app.get("/api/feedbacks")
async def get_feedbacks(_: bool = Depends(verify_password)):
    return {"feedbacks": list_feedbacks()}


@app.get("/api/project-rules")
async def get_project_rules(_: bool = Depends(verify_password)):
    if not config.arche_dir:
        return {"content": ""}
    rules_file = config.arche_dir / PROJECT_RULES
    return {"content": rules_file.read_text() if rules_file.exists() else ""}


@app.put("/api/project-rules")
async def update_project_rules(content: dict, _: bool = Depends(verify_password)):
    if not config.arche_dir:
        raise HTTPException(400, "No project configured")
    (config.arche_dir / PROJECT_RULES).write_text(content.get("content", ""))
    return {"status": "updated"}


@app.get("/api/state")
async def get_state(_: bool = Depends(verify_password)):
    return {"state": read_state()}


# WebSocket for real-time logs
@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()

    # Simple auth via first message
    if config.password_hash:
        try:
            auth = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            if hash_password(auth) != config.password_hash:
                await websocket.close(code=1008)
                return
        except:
            await websocket.close(code=1008)
            return

    config.log_connections.append(websocket)

    # Send current log content
    await websocket.send_text(json.dumps({"type": "init", "content": get_log_content()}))

    try:
        # Watch for new log content
        last_size = 0
        if config.arche_dir:
            log_file = config.arche_dir / LOG
            if log_file.exists():
                last_size = log_file.stat().st_size

        while True:
            await asyncio.sleep(0.5)
            if config.arche_dir:
                log_file = config.arche_dir / LOG
                if log_file.exists():
                    current_size = log_file.stat().st_size
                    if current_size > last_size:
                        with open(log_file, 'r') as f:
                            f.seek(last_size)
                            new_content = f.read()
                        last_size = current_size
                        await websocket.send_text(json.dumps({"type": "append", "content": new_content}))
    except WebSocketDisconnect:
        config.log_connections.remove(websocket)
    except:
        if websocket in config.log_connections:
            config.log_connections.remove(websocket)


# Agent execution loop (runs in background)
async def run_agent_loop(goal: str | None):
    """Main agent execution loop."""
    from arche.cli import (
        build_system_prompt, build_user_prompt, parse_reviewer_json,
        read_goal_from_plan, read_state as cli_read_state, write_state as cli_write_state,
        INFINITE, FORCE_REVIEW, FORCE_RETRO, STEP_MODE, PID, LOG
    )

    if not config.arche_dir or not config.project_root:
        return

    # Write PID
    pid_file = config.arche_dir / PID
    pid_file.write_text(str(os.getpid()))

    try:
        log_file = config.arche_dir / LOG
        infinite = (config.arche_dir / INFINITE).exists()

        state = cli_read_state(config.arche_dir)
        retro_config = state.get("retro_every", "auto")
        retro_every = int(retro_config) if str(retro_config).isdigit() else 0
        turn = state.get("turn", 1)
        plan_mode = state.get("plan_mode", False)
        goal = goal or read_goal_from_plan(config.arche_dir)
        next_task, journal_file = None, None

        engine_cfg = state.get("engine", {})
        engine_type = engine_cfg.get("type", "claude_sdk")
        base_engine_kwargs = dict(engine_cfg.get("kwargs", {}))
        base_engine_kwargs["cwd"] = config.project_root

        while True:
            state["turn"] = turn
            cli_write_state(config.arche_dir, state)

            # Determine mode
            resumed = False
            if (config.arche_dir / FORCE_RETRO).exists():
                (config.arche_dir / FORCE_RETRO).unlink()
                mode = "retro"
            elif (config.arche_dir / FORCE_REVIEW).exists():
                (config.arche_dir / FORCE_REVIEW).unlink()
                mode, resumed = "review", True
            elif retro_every > 0 and turn > 1 and turn % retro_every == 0:
                mode = "retro"
            elif turn == 1 and plan_mode:
                mode = "plan"
            else:
                if plan_mode:
                    mode = "review" if turn % 2 == 1 else "exec"
                else:
                    mode = "review" if turn % 2 == 0 else "exec"

            system_prompt = build_system_prompt(config.arche_dir, mode)
            user_prompt = build_user_prompt(turn, config.arche_dir, goal, mode, next_task, journal_file, resumed)

            engine_kwargs = dict(base_engine_kwargs)
            if engine_type == "claude_sdk":
                engine_kwargs["permission_mode"] = "bypassPermissions"
            engine = create_engine(engine_type, **engine_kwargs)
            config.current_engine = engine

            try:
                with open(log_file, "a") as f:
                    f.write(f"\n{'='*50}\nTurn {turn} ({mode.upper()}) - {datetime.now().isoformat()}\n{'='*50}\n")
                    f.flush()

                    output = ""
                    last_tool_ids = set()
                    last_was_tool = False

                    async for event in engine.run(goal=user_prompt, system_prompt=system_prompt):
                        if event.type == EventType.CONTENT and event.content:
                            output += event.content
                            f.write(event.content)
                            f.flush()
                            last_was_tool = False
                        elif event.type == EventType.TOOL_CALL:
                            tool_id = event.metadata.get("tool_id") if event.metadata else None
                            if tool_id and tool_id in last_tool_ids:
                                continue
                            if tool_id:
                                last_tool_ids.add(tool_id)
                            from arche.cli import _format_tool_args
                            args_str = _format_tool_args(event.tool_name, event.tool_args)
                            prefix = "\n" if not last_was_tool else ""
                            f.write(f"{prefix}[TOOL] {event.tool_name} {args_str}\n")
                            f.flush()
                            last_was_tool = True
                        elif event.type == EventType.ERROR:
                            f.write(f"\n*** Error: {event.error} ***\n")
                            f.flush()
                            last_was_tool = False

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

            except asyncio.CancelledError:
                with open(log_file, "a") as f:
                    f.write("\n*** Cancelled ***\n")
                break
            except Exception as e:
                with open(log_file, "a") as f:
                    f.write(f"\n*** Error: {e} ***\n")
                await asyncio.sleep(5)

    finally:
        pid_file.unlink(missing_ok=True)
        config.current_engine = None


def setup_server(project_path: Path, password: str | None = None):
    """Configure server for a project."""
    config.project_root = project_path.resolve()
    config.arche_dir = config.project_root / ".arche"
    config.arche_dir.mkdir(exist_ok=True)
    if password:
        config.password_hash = hash_password(password)
