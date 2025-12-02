## Global Rules

- Token efficiency: dense text, short titles, no verbose.
- File naming: `YYYYMMDD-HHMM-short-kebab-title.yaml`
- All state files are YAML.

## Layout

Directories inside `.arche/`:

- `journal/` - per turn logs
- `feedback/` - human input (`pending/`, `in_progress/`, `done/`)
- `plan/` - goals and tasks
- `retrospective/` - periodic project retrospectives
- `tools/` - reusable python tools

## Project Rules

Read `.arche/PROJECT_RULES.md` - project-specific coding, architecture, patterns, risks. Update when discovering new rules.
{% if tools %}
## Tools
Run: `python .arche/tools/<name>.py [args]`
Available: {{ tools }}
{% endif %}