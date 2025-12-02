<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'
import { useLogsWebSocket } from '@/composables/useWebSocket'
import LogPreview from '@/components/ui/LogPreview.vue'
import ControlPanel from '@/components/ui/ControlPanel.vue'
import StatusCard from '@/components/ui/StatusCard.vue'

const store = useAgentStore()
const { status, loading, error, logs } = storeToRefs(store)

// Connect to WebSocket for logs
useLogsWebSocket()

onMounted(() => {
  store.fetchStatus()
  // Poll status every 5 seconds
  const interval = setInterval(() => store.fetchStatus(), 5000)
  return () => clearInterval(interval)
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-mono text-[var(--color-text)]">Dashboard</h1>
      <span v-if="error" class="text-sm text-[var(--color-error)]">{{ error }}</span>
    </div>

    <!-- Status Card -->
    <StatusCard :status="status" :loading="loading" />

    <!-- Control Panel -->
    <ControlPanel />

    <!-- Live Log Preview -->
    <div class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] overflow-hidden">
      <div class="px-4 py-2 border-b border-[var(--color-border)] flex items-center justify-between">
        <h2 class="text-sm font-mono text-[var(--color-text-muted)]">Live Logs</h2>
        <RouterLink
          to="/logs"
          class="text-xs text-[var(--color-accent)] hover:underline font-mono"
        >
          Full View →
        </RouterLink>
      </div>
      <LogPreview :content="logs" :maxLines="20" />
    </div>
  </div>
</template>
