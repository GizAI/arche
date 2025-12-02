Turn {{ turn }}. Mode: {{ "REVIEW" if review_mode else "EXEC" }}.
{% if goal %}Goal: {{ goal }}{% endif %}
{% if review_mode %}
{% if resumed %}
**Resumed.** Check current state from journal/plan before continuing.
{% endif %}
## Previous Execution Journal
{{ prev_journal }}
{% else %}
## Task
{{ next_task }}
{% if context_journal %}
## Context
{{ context_journal }}
{% endif %}
{% endif %}
