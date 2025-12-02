# Arche

Long-lived coding agent that runs Claude Code in a loop with alternating execution and review modes.

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
│      ├── RULE_EXEC.md  ← Execution mode system prompt       │
│      ├── RULE_REVIEW.md← Review mode system prompt          │
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

## Execution/Review Mode Alternation

Arche alternates between two modes:

```
Turn 1 (EXEC)  → Turn 2 (REVIEW) → Turn 3 (EXEC) → Turn 4 (REVIEW) → ...
```

### Execution Mode (Odd Turns)

- Focus on task execution
- Write code, create files, run commands
- Do NOT test or verify - that's for review mode
- Mark task as done when complete
- Uses `RULE_EXEC.md` as system prompt

### Review Mode (Even Turns)

- Review previous execution
- Test thoroughly with Playwright MCP
- Verify UI functionality, test edge cases
- Document issues found
- Update plan with rework items if needed
- Uses `RULE_REVIEW.md` as system prompt

This ensures Claude Code actually completes work (not just claims to).

## Flow

### 1. Start

```bash
arche start "goal"
```

- Creates `.arche/` directory if not exists
- Copies `RULE_EXEC.md` and `RULE_REVIEW.md` into `.arche/`
- Spawns background daemon process
- Daemon runs Claude Code in alternating exec/review loop

### 2. Turn Loop

```
Turn 1 (EXEC): goal → execute → write journal
Turn 2 (REVIEW): read journal → test → output JSON {next_task, journal_file}
Turn 3 (EXEC): next_task + journal → execute → write journal
Turn 4 (REVIEW): read journal → test → output JSON
...
```

The **reviewer controls the loop**:
- Decides what the next task is
- Specifies which journal file to pass as context
- Outputs `"status": "done"` when all work is complete

### 3. Exit Condition

**Task mode** (default):
- Exits when reviewer outputs `{"status": "done", ...}`
- Only outputs "done" when ALL work is verified complete

**Infinite mode** (`--infinite`):
- Never exits
- After goal achieved, reviewer finds next goal

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
│  (typer)     │     │  (turn loop) │     │   (claude)   │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                     Turn 1: EXEC mode           │
                     Turn 2: REVIEW mode         ▼
                     Turn 3: EXEC mode     ┌──────────┐
                     ...                   │ .arche/  │
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
- Alternating modes ensure work is actually done and verified

## Claude Code Invocation

Each turn, Claude Code is called with mode-specific prompts:

### Execution Turn (Odd)

```bash
claude --print \
       --permission-mode plan \
       --system-prompt "$(cat .arche/RULE_EXEC.md)" \
       [extra args] \
       "Turn 1. Mode: EXEC.
        Goal: Build a todo app.
        ## Task
        [next_task from reviewer, or goal on turn 1]
        ## Context
        [journal file specified by reviewer]"
```

### Review Turn (Even)

```bash
claude --print \
       --permission-mode plan \
       --system-prompt "$(cat .arche/RULE_REVIEW.md)" \
       [extra args] \
       "Turn 2. Mode: REVIEW.
        ## Previous Execution Journal
        [latest journal from exec turn]"
```

### Reviewer JSON Response

After testing, the reviewer outputs:

```json
{
  "status": "continue",
  "next_task": "Fix the login validation bug",
  "journal_file": "journal/20241201-1430-auth.yaml"
}
```

This controls what the next executor receives.

### Default Options

| Option | Purpose |
|--------|---------|
| `--print` | Non-interactive mode, outputs to stdout |
| `--permission-mode plan` | Plan mode (default) - Claude plans before executing |
| `--system-prompt` | Pass RULE_EXEC.md or RULE_REVIEW.md content |

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
| `--permission-mode <mode>` | Override permission mode |

Extra args are saved to `.arche/claude_args.json` and reused on `resume`.

### Working Directory

Claude Code runs with `cwd = .arche/`, so:
- RULE files are in current directory
- User project files are accessed via `../` (parent directory)

## Templates

All prompt files are Jinja2 templates:

**RULE_EXEC.md / RULE_REVIEW.md variables:**
- `infinite` (bool) - Filters instructions for infinite mode

**PROMPT.md variables:**
- `turn` (int) - Current turn number
- `goal` (str) - Initial goal (first turn only)
- `review_mode` (bool) - True for review turns
- `next_task` (str) - Task from reviewer (exec mode)
- `context_journal` (str) - Journal specified by reviewer (exec mode)
- `prev_journal` (str) - Latest journal (review mode)

## Files

| File | Purpose |
|------|---------|
| `src/arche/cli.py` | CLI commands (start, stop, resume, log, status, feedback) |
| `src/arche/RULE_EXEC.md` | Execution mode system prompt template |
| `src/arche/RULE_REVIEW.md` | Review mode system prompt template |
| `src/arche/PROMPT.md` | User prompt Jinja2 template |
| `pyproject.toml` | Package config |

## License

MIT
