# Arche

Long-lived coding agent that runs Claude Code in a loop.

## Install

```bash
pip install -e .
```

## Usage

```bash
# Start with a goal
arche start "Build a todo app with Vue3 frontend and FastAPI backend"

# Start in infinite mode (keeps finding new goals)
arche start "Improve this codebase" --infinite

# Pass claude options after --
arche start "goal" -- --model opus
arche start "goal" -- --add-dir ../other-project
arche start "goal" -- --dangerously-skip-permissions

# Stop running agent
arche stop

# Resume stopped agent (uses saved claude args)
arche resume

# View logs
arche log              # real-time (tail -f)
arche log --no-follow  # static view
arche log --clear      # clear log

# Check status
arche status

# Send feedback to agent
arche feedback "Fix the login bug first" --priority high
```

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  your-project/                                              │
│  ├── src/                                                   │
│  ├── ...                                                    │
│  └── .arche/           ← Arche's workspace (cwd for Claude) │
│      ├── RULE.md       ← System prompt (Arche's rules)      │
│      ├── arche.log     ← Real-time output log               │
│      ├── arche.pid     ← Process ID file                    │
│      ├── infinite      ← Flag file (exists = infinite mode) │
│      ├── claude_args.json ← Saved claude CLI args           │
│      ├── journal/      ← Turn-by-turn logs (YAML)           │
│      ├── feedback/     ← Human feedback queue               │
│      │   ├── pending/                                       │
│      │   ├── in_progress/                                   │
│      │   └── done/                                          │
│      ├── plan/         ← Goals and tasks (YAML)             │
│      ├── lib/          ← Knowledge library (YAML)           │
│      └── tools/        ← Python tools Arche creates         │
└─────────────────────────────────────────────────────────────┘
```

## Flow

### 1. Start

```bash
arche start "goal"
```

- Creates `.arche/` directory if not exists
- Copies `RULE.md` (system prompt) into `.arche/`
- Spawns background daemon process
- Daemon runs Claude Code in a loop (turn-based)

### 2. Turn Loop

Each turn:

1. Read latest journal (previous turn's state)
2. Process pending feedback (`feedback/pending/` → `in_progress/`)
3. Load relevant plan files
4. Execute one unit of work
5. Write journal entry for this turn
6. Move processed feedback to `done/`
7. Check exit condition

### 3. Exit Condition

**Task mode** (default):
- Exits when Claude outputs `ARCHE_DONE`
- Only outputs `ARCHE_DONE` when ALL work is complete:
  - Goal achieved
  - No pending feedback
  - No active plan items

**Infinite mode** (`--infinite`):
- Never exits
- After `ARCHE_DONE`, finds next goal and continues

### 4. Resume

```bash
arche resume
```

- Restarts the daemon
- Claude reads its own state from `plan/`, `journal/`, `feedback/`
- Continues where it left off

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  arche CLI   │────▶│    Daemon    │────▶│ Claude Code  │
│  (typer)     │     │  (loop.py)   │     │   (claude)   │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            │                    ▼
                            │              ┌──────────┐
                            │              │ .arche/  │
                            │              │  - YAML  │
                            │              │  - tools │
                            └─────────────▶│  - logs  │
                                           └──────────┘
```

**Key design:**
- Arche CLI just manages the daemon lifecycle
- All state lives in `.arche/` as YAML files
- Claude Code manages its own state (plan, journal, feedback)
- Human can add feedback anytime via `arche feedback`

## Claude Code Invocation

Each turn, Claude Code is called like this:

```bash
claude --print \
       --permission-mode plan \
       --system-prompt "$(cat .arche/RULE.md)" \
       [extra args from start] \
       "Turn 1. Goal: Build a todo app. Mode: task (exit on ARCHE_DONE)"
```

### Default Options

| Option | Purpose |
|--------|---------|
| `--print` | Non-interactive mode, outputs to stdout |
| `--permission-mode plan` | Plan mode (default) - Claude plans before executing |
| `--system-prompt` | Pass RULE.md content as system prompt |

### Pass-through Options

All claude CLI options can be passed after `--`:

```bash
arche start "goal" -- --model opus --dangerously-skip-permissions
```

Common options:
| Option | Purpose |
|--------|---------|
| `--model <model>` | Use specific model (opus, sonnet, haiku) |
| `--dangerously-skip-permissions` | Auto-approve all tool calls |
| `--add-dir <dir>` | Additional directories to allow access |
| `--permission-mode <mode>` | Override permission mode (acceptEdits, bypassPermissions, default, plan) |

Extra args are saved to `.arche/claude_args.json` and reused on `resume`.

### Working Directory

Claude Code runs with `cwd = .arche/`, so:
- RULE.md is in current directory
- User project files are accessed via `../` (parent directory)

## Files

| File | Purpose |
|------|---------|
| `src/arche/cli.py` | CLI commands (start, stop, resume, log, status, feedback) |
| `src/arche/RULE.md` | System prompt template (copied to .arche/) |
| `src/arche/PROMPT.md` | Jinja2 prompt template |
| `pyproject.toml` | Package config |

## License

MIT
