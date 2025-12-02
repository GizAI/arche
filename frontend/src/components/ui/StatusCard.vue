<script setup lang="ts">
import { computed } from 'vue'
import type { AgentStatus } from '@/stores/agent'

const props = defineProps<{
  status: AgentStatus | null
  loading: boolean
}>()

const statusBadge = computed(() => {
  if (!props.status) return { text: 'Unknown', color: 'var(--color-text-subtle)', bg: 'var(--color-bg-muted)' }
  if (props.status.running) {
    if (props.status.paused) {
      return { text: 'Paused', color: 'var(--color-warning)', bg: 'rgba(234, 179, 8, 0.1)' }
    }
    return { text: 'Running', color: 'var(--color-success)', bg: 'rgba(34, 197, 94, 0.1)' }
  }
  return { text: 'Stopped', color: 'var(--color-text-subtle)', bg: 'var(--color-bg-muted)' }
})
</script>

<template>
  <div class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] p-6">
    <div v-if="!status" class="text-center text-[var(--color-text-muted)]">
      Loading status...
    </div>

    <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-6">
      <!-- Status -->
      <div>
        <div class="text-xs text-[var(--color-text-subtle)] mb-1 font-mono">STATUS</div>
        <div
          class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-mono"
          :style="{ backgroundColor: statusBadge.bg, color: statusBadge.color }"
        >
          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: statusBadge.color }" />
          {{ statusBadge.text }}
        </div>
      </div>

      <!-- Turn -->
      <div>
        <div class="text-xs text-[var(--color-text-subtle)] mb-1 font-mono">TURN</div>
        <div class="text-2xl font-mono text-[var(--color-text)]">{{ status.turn }}</div>
      </div>

      <!-- Mode -->
      <div>
        <div class="text-xs text-[var(--color-text-subtle)] mb-1 font-mono">MODE</div>
        <div class="text-sm font-mono text-[var(--color-text)]">
          {{ status.mode.toUpperCase() }}
          <span v-if="status.last_mode" class="text-[var(--color-text-muted)]">
            (last: {{ status.last_mode }})
          </span>
        </div>
      </div>

      <!-- Engine -->
      <div>
        <div class="text-xs text-[var(--color-text-subtle)] mb-1 font-mono">ENGINE</div>
        <div class="text-sm font-mono text-[var(--color-text)]">{{ status.engine }}</div>
      </div>

      <!-- Goal (full width) -->
      <div class="col-span-2 md:col-span-4">
        <div class="text-xs text-[var(--color-text-subtle)] mb-1 font-mono">GOAL</div>
        <div class="text-sm text-[var(--color-text)] font-mono bg-[var(--color-bg-muted)] px-3 py-2 rounded">
          {{ status.goal || 'No goal set' }}
        </div>
      </div>

      <!-- Flags -->
      <div class="col-span-2 md:col-span-4 flex gap-4">
        <div v-if="status.infinite" class="text-xs font-mono px-2 py-1 rounded bg-[var(--color-bg-muted)] text-[var(--color-warning)]">
          ∞ Infinite
        </div>
        <div v-if="status.step" class="text-xs font-mono px-2 py-1 rounded bg-[var(--color-bg-muted)] text-[var(--color-info)]">
          Step Mode
        </div>
        <div v-if="status.pid" class="text-xs font-mono px-2 py-1 rounded bg-[var(--color-bg-muted)] text-[var(--color-text-muted)]">
          PID: {{ status.pid }}
        </div>
      </div>
    </div>
  </div>
</template>
