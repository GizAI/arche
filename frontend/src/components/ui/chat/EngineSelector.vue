<script setup lang="ts">
import { computed } from 'vue'
import type { EngineType } from '@/stores/interactive'

const props = defineProps<{
  modelValue: EngineType
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: EngineType]
}>()

const engines = [
  { value: 'claude_sdk', label: 'Claude SDK', description: 'Direct Claude API integration' },
  { value: 'deepagents', label: 'DeepAgents', description: 'Full agentic capabilities' },
] as const

const selectedEngine = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
</script>

<template>
  <div class="engine-selector">
    <select
      v-model="selectedEngine"
      :disabled="disabled"
      class="engine-select"
    >
      <option
        v-for="engine in engines"
        :key="engine.value"
        :value="engine.value"
      >
        {{ engine.label }}
      </option>
    </select>
    <span class="engine-badge" :class="{ deepagents: modelValue === 'deepagents' }">
      {{ modelValue === 'deepagents' ? 'Agent' : 'SDK' }}
    </span>
  </div>
</template>

<style scoped>
.engine-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.engine-select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  background: var(--bg-color, #1a1a1a);
  color: var(--text-color, #e0e0e0);
  font-size: 0.875rem;
  cursor: pointer;
}

.engine-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.engine-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  background: var(--badge-bg, #333);
  color: var(--badge-color, #888);
}

.engine-badge.deepagents {
  background: var(--accent-color, #5a67d8);
  color: white;
}
</style>
