# Arche

**Long-lived coding agent** that runs autonomously in plan → exec → review cycles until your goal is achieved.

## Why Arche?

| Feature | Benefit |
|---------|---------|
| **Self-correcting loop** | Exec → Review → Fix → Repeat. No more "it works on my machine" |
| **Persistent context** | Resumes from where it stopped. Multi-day projects? No problem |
| **Human-in-the-loop** | Send feedback anytime. Agent adapts without restart |
| **Quality gates** | Built-in checklist (UX, mobile, access, bugs) before marking done |
| **Project memory** | Learns your patterns in `PROJECT_RULES.md`, gets smarter over time |
| **Hands-free execution** | Start and walk away. Check back when it's done |

```bash
arche start "Build a SaaS dashboard with auth, billing, and analytics"
# Go grab a coffee. Come back to a working app.
```

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# Start with a goal (exec → review → exec → review ...)
arche start "Build a todo app with Vue3 and FastAPI"

# Start with planning phase first (plan → exec → review ...)
arche start --plan "Build a todo app with Vue3 and FastAPI"

# Use specific model
arche start -m opus "Refactor authentication system"

# Infinite mode (keeps improving after completion)
arche start --infinite "Improve this codebase"

# Step mode (one task at a time, careful review)
arche start --step "Implement all API endpoints"
```

## Commands

```bash
# Core
arche start <goal>       # Start new session
arche stop               # Stop running agent
arche resume             # Resume from last turn
arche resume -r          # Resume with review mode
arche resume -R          # Resume with retrospective mode
arche resume "Fix bug"   # Resume with feedback
arche status             # Check if running
arche log                # View real-time logs (Ctrl+C to detach)
arche log --no-follow    # View static log

# Feedback
arche feedback "msg"     # Send feedback to agent
arche feedback -p high   # High priority feedback
arche feedback --now     # Trigger immediate review

# Web UI Server
arche serve start        # Start web UI (background)
arche serve start -f     # Start in foreground
arche serve stop         # Stop server
arche serve restart      # Restart server
arche serve status       # Check server status
arche serve log          # View server logs

# Templates
arche templates          # Copy all templates to .arche/templates/
arche templates -l       # List templates (✓ = customized)
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

```
EXEC → REVIEW → EXEC → REVIEW → ... → DONE
         ↑         ↓
         └─ fix ───┘
```

With `--plan`:
```
PLAN → EXEC → REVIEW → EXEC → REVIEW → ... → DONE
```

The agent alternates: after exec comes review, after review comes exec. Simple.

### Modes

| Mode | Purpose |
|------|---------|
| **PLAN** | Analyze goal, explore codebase, create detailed plan |
| **EXEC** | Execute tasks, write code, run commands |
| **REVIEW** | Test execution, verify completeness, update plan |
| **RETRO** | Periodic retrospective, update PROJECT_RULES.md |

### Done Checklist

Before marking "done", the agent must verify:

| Check | Description |
|-------|-------------|
| `goal_met` | Original goal achieved |
| `feedback_done` | All user feedback addressed |
| `usable` | User can actually USE it (not just "works technically") |
| `flow` | No dead-ends in user flow |
| `ui_ux` | UI/UX works correctly |
| `mobile` | Mobile-friendly UX |
| `access` | Access info complete (URL + credentials/signup) |
| `bug_free` | No bugs found in testing |
| `clean` | No dead/duplicate code |

Done is rejected until all checks pass.

## Directory Structure

```
your-project/
├── src/
├── ...
└── .arche/                    ← Arche's workspace
    ├── state.json             ← Session state (turn, mode, etc.)
    ├── arche.log              ← Real-time output
    ├── arche.pid              ← Agent process ID
    ├── server.pid             ← Web UI server PID
    ├── templates/             ← Customizable templates (arche templates)
    │   ├── RULE_PROJECT.md    ← Project-specific rules
    │   ├── RULE_*.md          ← Mode-specific prompts
    │   ├── PROMPT.md          ← User prompt template
    │   └── CHECKLIST.yaml     ← Done checklist items
    ├── journal/               ← Turn-by-turn logs (YAML)
    ├── plan/                  ← Goals and tasks (YAML)
    ├── feedback/              ← Human feedback
    │   └── archive/           ← Processed feedback
    ├── retrospective/         ← Periodic retrospectives
    └── tools/                 ← Reusable Python tools
```

## Feedback System

Send feedback anytime - it's auto-injected into the next review prompt:

```bash
# Normal priority
arche feedback "Focus on mobile responsiveness"

# High priority
arche feedback "Critical: fix login bug" -p high

# Trigger immediate review
arche feedback "Review my changes" --now

# Or send with resume
arche resume "Add dark mode support"
```

Feedback is archived after processing.

## Customization

Run `arche templates` to copy all templates to `.arche/templates/` for customization:

| Template | Purpose |
|----------|---------|
| `RULE_PROJECT.md` | Project-specific rules (coding standards, architecture) |
| `RULE_EXEC.md` | Instructions for exec mode |
| `RULE_REVIEW.md` | Instructions for review/plan mode |
| `RULE_RETRO.md` | Instructions for retrospective mode |
| `RULE_COMMON.md` | Shared context for all modes |
| `PROMPT.md` | User prompt template |
| `CHECKLIST.yaml` | Done checklist items |

Templates in `.arche/templates/` override defaults. The agent updates `RULE_PROJECT.md` during retrospectives.

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
  "engine": {"type": "claude_sdk", "kwargs": {"model": "opus"}},
  "turn": 5,
  "last_mode": "exec",
  "next_task": "Implement user authentication",
  "journal_file": ".arche/journal/20241201-1430-auth.yaml"
}
```

## License

MIT
