## Global Rules

- Token efficiency: dense text, short titles, no verbose.
- File naming: `YYYYMMDD-HHMM-short-kebab-title.yaml`
- All state files are YAML.

## Layout

Directories inside `.arche/`:

- `journal/` - per turn logs
- `feedback/` - human input (`pending/`, `in_progress/`, `done/`)
- `plan/` - goals and tasks
- `tools/` - reusable python tools
{% if tools %}
## Tools
Run: `python .arche/tools/<name>.py [args]`
Available: {{ tools }}
{% endif %}