# Arche

Long-lived coding agent that runs in a loop with plan → exec → review cycles.

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# Start with a goal (exec → review → exec → review ...)
arche start "Build a todo app with Vue3 and FastAPI"

# Start with planning phase first (plan → exec → review → exec → review ...)
arche start --plan "Build a todo app with Vue3 and FastAPI"

# Use specific model
arche start -m opus "Refactor authentication system"

# Infinite mode (keeps finding new goals after completion)
arche start --infinite "Improve this codebase"

# Step mode (one task at a time, careful review)
arche start --step "Implement all API endpoints"
```

## Commands

```bash
arche start <goal>       # Start new session
arche stop               # Stop running agent
arche resume             # Resume from last turn
arche resume -r          # Resume with review mode
arche resume -R          # Resume with retrospective mode
arche resume Fix the bug  # Resume with feedback
arche log                # View real-time logs (Ctrl+C to detach)
arche log --no-follow    # View static log
arche status             # Check if running
arche feedback "msg"     # Send feedback to agent
arche feedback --now     # Send feedback and trigger immediate review
arche version            # Show version
```

## Start Options

| Option | Description |
|--------|-------------|
| `-p, --plan` | Start with plan mode first |
| `-e, --engine` | Engine: claude_sdk (default), deepagents, codex |
| `-m, --model` | Model to use (e.g., opus, sonnet) |
| `-i, --infinite` | Run infinitely, find new goals after completion |
| `-s, --step` | Process one task at a time |
| `-r, --retro-every` | Retro schedule: auto, N (every N turns), off |
| `-f, --force` | Force restart if already running |

## How It Works

### Turn Cycle

**Without --plan:**
```
Turn 1 (EXEC) → Turn 2 (REVIEW) → Turn 3 (EXEC) → Turn 4 (REVIEW) → ...
```

**With --plan:**
```
Turn 1 (PLAN) → Turn 2 (EXEC) → Turn 3 (REVIEW) → Turn 4 (EXEC) → ...
```

### Modes

| Mode | Purpose |
|------|---------|
| **PLAN** | Analyze goal, explore codebase, create detailed plan |
| **EXEC** | Execute tasks, write code, run commands |
| **REVIEW** | Test execution, verify completeness, update plan |
| **RETRO** | Periodic retrospective, update PROJECT_RULES.md |

### Reviewer Controls the Loop

After each review, the agent outputs JSON:
```json
{
  "status": "continue",
  "next_task": "Implement user authentication",
  "journal_file": ".arche/journal/20241201-1430-auth.yaml"
}
```

When complete:
```json
{
  "status": "done"
}
```

## Directory Structure

```
your-project/
├── src/
├── ...
└── .arche/                    ← Arche's workspace
    ├── state.json             ← Session state
    ├── arche.log              ← Real-time output
    ├── arche.pid              ← Process ID
    ├── PROJECT_RULES.md       ← Project-specific rules (included in prompts)
    ├── journal/               ← Turn-by-turn logs (YAML)
    ├── plan/                  ← Goals and tasks (YAML)
    ├── feedback/              ← Human feedback (processed → archive/)
    ├── retrospective/         ← Periodic retrospectives
    └── tools/                 ← Reusable Python tools
```

## Feedback System

Send feedback anytime:
```bash
# Normal priority
arche feedback "Focus on mobile responsiveness"

# High priority
arche feedback "Critical: fix login bug" -p high

# Trigger immediate review
arche feedback "Review my changes" --now
```

Agent processes feedback and moves to `archive/`.

## Project Rules

Edit `.arche/PROJECT_RULES.md` to customize agent behavior:
- Coding standards
- Architecture patterns
- Known risks/constraints
- Project-specific instructions

This file is included directly in every system prompt.

## Engine Architecture

Arche supports pluggable AI engines:

| Engine | Description |
|--------|-------------|
| `claude_sdk` | Claude Agent SDK (default) |
| `deepagents` | DeepAgents framework |
| `codex` | OpenAI Codex |

```bash
arche start -e deepagents "Build API"
```

## State Management

Session state is stored in `.arche/state.json`:
```json
{
  "goal": "Build a todo app with Vue3 and FastAPI",
  "engine": {"type": "claude_sdk", "kwargs": {"model": "opus"}},
  "retro_every": "auto",
  "turn": 5,
  "plan_mode": true,
  "next_task": "Implement user authentication",
  "journal_file": ".arche/journal/20241201-1430-auth.yaml"
}
```

## License

MIT
