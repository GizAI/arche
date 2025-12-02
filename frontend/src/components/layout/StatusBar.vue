<script setup lang="ts">
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

const store = useAgentStore()
const { status, wsConnected } = storeToRefs(store)

const statusColor = computed(() => {
  if (!status.value) return 'var(--color-text-subtle)'
  if (status.value.running) {
    if (status.value.paused) return 'var(--color-warning)'
    return 'var(--color-success)'
  }
  return 'var(--color-text-subtle)'
})

const statusText = computed(() => {
  if (!status.value) return 'Loading...'
  if (status.value.running) {
    if (status.value.paused) return 'PAUSED'
    return 'RUNNING'
  }
  return 'STOPPED'
})
</script>

<template>
  <header class="h-10 bg-[var(--color-bg-subtle)] border-b border-[var(--color-border)] flex items-center justify-between px-4">
    <!-- Left: Status indicator -->
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2">
        <span
          class="w-2 h-2 rounded-full"
          :style="{ backgroundColor: statusColor }"
        />
        <span class="text-xs font-mono" :style="{ color: statusColor }">
          {{ statusText }}
        </span>
      </div>

      <template v-if="status">
        <span class="text-[var(--color-border)]">│</span>
        <span class="text-xs text-[var(--color-text-muted)] font-mono">
          Turn {{ status.turn }}
        </span>
        <span v-if="status.last_mode" class="text-xs text-[var(--color-text-subtle)] font-mono">
          ({{ status.last_mode }})
        </span>
      </template>
    </div>

    <!-- Right: Connection status & info -->
    <div class="flex items-center gap-3 text-xs font-mono">
      <span v-if="status?.infinite" class="text-[var(--color-warning)]">∞</span>
      <span v-if="status?.step" class="text-[var(--color-info)]">STEP</span>
      <div class="flex items-center gap-1">
        <span
          class="w-1.5 h-1.5 rounded-full"
          :class="wsConnected ? 'bg-[var(--color-success)]' : 'bg-[var(--color-error)]'"
        />
        <span class="text-[var(--color-text-subtle)]">
          {{ wsConnected ? 'CONNECTED' : 'DISCONNECTED' }}
        </span>
      </div>
    </div>
  </header>
</template>
