<script setup lang="ts">
import { computed } from 'vue'
import type { AgentCapability } from '@/stores/interactive'

const props = defineProps<{
  modelValue: AgentCapability[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AgentCapability[]]
}>()

const capabilities = [
  { value: 'filesystem', label: 'Files', icon: '📁', description: 'Read/write files' },
  { value: 'planning', label: 'Plan', icon: '📋', description: 'Todo list tracking' },
  { value: 'subagent', label: 'Agents', icon: '🤖', description: 'Spawn sub-agents' },
  { value: 'summarization', label: 'Summary', icon: '📝', description: 'Context summarization' },
] as const

function isEnabled(cap: AgentCapability): boolean {
  return props.modelValue.includes(cap)
}

function toggle(cap: AgentCapability) {
  if (props.disabled) return

  const newValue = isEnabled(cap)
    ? props.modelValue.filter(c => c !== cap)
    : [...props.modelValue, cap]

  emit('update:modelValue', newValue)
}
</script>

<template>
  <div class="capability-toggles">
    <button
      v-for="cap in capabilities"
      :key="cap.value"
      :class="['cap-toggle', { active: isEnabled(cap.value as AgentCapability), disabled }]"
      :title="cap.description"
      @click="toggle(cap.value as AgentCapability)"
    >
      <span class="cap-icon">{{ cap.icon }}</span>
      <span class="cap-label">{{ cap.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.capability-toggles {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.cap-toggle {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border-color, #333);
  border-radius: 9999px;
  background: var(--bg-color, #1a1a1a);
  color: var(--text-muted, #888);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.cap-toggle:hover:not(.disabled) {
  border-color: var(--border-hover, #555);
}

.cap-toggle.active {
  background: var(--accent-bg, rgba(90, 103, 216, 0.2));
  border-color: var(--accent-color, #5a67d8);
  color: var(--text-color, #e0e0e0);
}

.cap-toggle.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cap-icon {
  font-size: 0.875rem;
}

.cap-label {
  font-weight: 500;
}
</style>
