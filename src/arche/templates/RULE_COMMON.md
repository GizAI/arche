## General
- Token efficiency: dense text, short titles, no verbose.
- File naming: `YYYYMMDD-HHMM-short-kebab-title.yaml`
- No commit/push without explicit user request.

## Layout

Directories inside `.arche/`:

- `journal/` - per turn logs
- `feedback/` - human input (processed → `archive/`)
- `plan/` - goals and tasks
- `retrospective/` - periodic project retrospectives
- `tools/` - reusable python tools
{% if tools %}
## Tools
Run: `python .arche/tools/<name>.py [args]`
Available: {{ tools }}
{% endif %}
## Project Rules

{{ project_rules }}