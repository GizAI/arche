Turn {{ turn }}. Mode: {{ "REVIEW" if review_mode else "EXEC" }}.
{% if goal %}Goal: {{ goal }}{% endif %}
{% if review_mode %}
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
