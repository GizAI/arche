Turn {{ turn }}. Mode: {{ mode | upper }}.
{% if goal %}Goal: {{ goal }}{% endif %}
{% if feedback %}

## User Feedback (address these first)
{{ feedback }}
{% endif %}
{% if mode == "plan" %}

Create a detailed plan. Do NOT execute.
{% elif mode == "retro" %}

Conduct retrospective. Update PROJECT_RULES.md.
{% elif mode == "review" %}

## Previous Journal
{{ prev_journal }}
{% else %}

## Task
{{ next_task or goal or "Continue with the plan" }}
{% if context_journal %}

## Context
{{ context_journal }}
{% endif %}
{% endif %}
