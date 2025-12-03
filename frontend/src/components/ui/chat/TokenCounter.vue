<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  input: number
  output: number
}>()

const total = computed(() => props.input + props.output)

// Rough cost estimation (Claude Sonnet pricing)
const estimatedCost = computed(() => {
  const inputCost = (props.input / 1000000) * 3  // $3/1M input tokens
  const outputCost = (props.output / 1000000) * 15  // $15/1M output tokens
  return inputCost + outputCost
})

function formatNumber(n: number): string {
  if (n >= 1000000) {
    return (n / 1000000).toFixed(1) + 'M'
  }
  if (n >= 1000) {
    return (n / 1000).toFixed(1) + 'K'
  }
  return n.toString()
}
</script>

<template>
  <div class="token-counter" :title="`Input: ${input} | Output: ${output}`">
    <div class="token-stat">
      <span class="token-label">In</span>
      <span class="token-value">{{ formatNumber(input) }}</span>
    </div>
    <div class="token-divider">/</div>
    <div class="token-stat">
      <span class="token-label">Out</span>
      <span class="token-value">{{ formatNumber(output) }}</span>
    </div>
    <div class="token-cost" v-if="total > 0">
      ~${{ estimatedCost.toFixed(4) }}
    </div>
  </div>
</template>

<style scoped>
.token-counter {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background: var(--bg-secondary, #252525);
  font-size: 0.75rem;
  color: var(--text-muted, #888);
}

.token-stat {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.token-label {
  color: var(--text-muted, #666);
}

.token-value {
  font-weight: 600;
  color: var(--text-color, #e0e0e0);
  font-family: monospace;
}

.token-divider {
  color: var(--text-muted, #444);
}

.token-cost {
  padding-left: 0.5rem;
  border-left: 1px solid var(--border-color, #333);
  color: var(--accent-color, #5a67d8);
  font-weight: 500;
}
</style>
