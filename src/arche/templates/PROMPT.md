Turn {{ turn }}. Mode: {{ mode | upper }}.
{% if goal %}Goal: {{ goal }}{% endif %}
{% if feedback %}

## User Feedback
{{ feedback }}
{% endif %}
{% if mode == "plan" %}

Create a detailed plan. Do NOT execute.
{% elif mode == "retro" %}

Conduct retrospective. Update RULE_PROJECT.md.
{% elif mode == "review" %}

## Previous Journal
{{ prev_journal }}
{% else %}

## Task
{{ next_task or "See feedback above" }}
{% if context_journal %}

## Context
{{ context_journal }}
{% endif %}
{% endif %}
