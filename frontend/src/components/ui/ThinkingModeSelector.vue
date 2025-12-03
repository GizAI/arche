<script setup lang="ts">
import { computed } from 'vue'
import { useInteractiveStore, type ThinkingMode } from '@/stores/interactive'

const store = useInteractiveStore()

const modes: { value: ThinkingMode; label: string; description: string; tokens: string }[] = [
  { value: 'normal', label: 'Normal', description: 'Standard response', tokens: '-' },
  { value: 'think', label: 'Think', description: 'Light reasoning', tokens: '10K' },
  { value: 'think_hard', label: 'Think Hard', description: 'Deep reasoning', tokens: '50K' },
  { value: 'ultrathink', label: 'Ultrathink', description: 'Maximum reasoning', tokens: '100K' },
]

const currentMode = computed(() => store.thinkingMode)

async function selectMode(mode: ThinkingMode) {
  await store.setThinkingMode(mode)
}
</script>

<template>
  <div class="thinking-mode-selector">
    <div class="mode-label">Thinking</div>
    <div class="mode-buttons">
      <button
        v-for="mode in modes"
        :key="mode.value"
        :class="['mode-btn', { active: currentMode === mode.value }]"
        :title="`${mode.description} (${mode.tokens} tokens)`"
        @click="selectMode(mode.value)"
      >
        <span class="mode-name">{{ mode.label }}</span>
        <span v-if="mode.tokens !== '-'" class="mode-tokens">{{ mode.tokens }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.thinking-mode-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-label {
  font-size: 12px;
  color: var(--color-text-secondary, #666);
  font-weight: 500;
}

.mode-buttons {
  display: flex;
  gap: 4px;
  background: var(--color-bg-secondary, #f5f5f5);
  border-radius: 6px;
  padding: 2px;
}

.mode-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 10px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
  min-width: 60px;
}

.mode-btn:hover {
  background: var(--color-bg-hover, rgba(0, 0, 0, 0.05));
}

.mode-btn.active {
  background: var(--color-primary, #4f46e5);
  color: white;
}

.mode-name {
  font-size: 11px;
  font-weight: 500;
}

.mode-tokens {
  font-size: 9px;
  opacity: 0.7;
  margin-top: 1px;
}

@media (max-width: 640px) {
  .thinking-mode-selector {
    flex-direction: column;
    align-items: flex-start;
  }

  .mode-btn {
    min-width: 50px;
    padding: 3px 6px;
  }

  .mode-name {
    font-size: 10px;
  }
}
</style>
