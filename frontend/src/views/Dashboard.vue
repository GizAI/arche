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

// Page load animation state
const animated = ref(false)

onMounted(() => {
  store.fetchStatus()
  // Poll status every 5 seconds
  const interval = setInterval(() => store.fetchStatus(), 5000)

  // Trigger stagger animation
  setTimeout(() => {
    animated.value = true
  }, 50)

  return () => clearInterval(interval)
})
</script>

<template>
  <div class="h-full flex flex-col space-y-6 p-6">
    <!-- Header -->
    <div
      class="flex items-center justify-between stagger-item"
      :class="{ 'stagger-animate': animated }"
      style="--stagger-delay: 0"
    >
      <h1 class="text-xl font-mono text-[var(--color-text)]">Dashboard</h1>
      <span v-if="error" class="text-sm text-[var(--color-error)]">{{ error }}</span>
    </div>

    <!-- Status Card -->
    <div
      class="stagger-item"
      :class="{ 'stagger-animate': animated }"
      style="--stagger-delay: 1"
    >
      <StatusCard :status="status" :loading="loading" />
    </div>

    <!-- Control Panel -->
    <div
      class="stagger-item"
      :class="{ 'stagger-animate': animated }"
      style="--stagger-delay: 2"
    >
      <ControlPanel />
    </div>

    <!-- Live Log Preview -->
    <div
      class="flex-1 min-h-0 flex flex-col bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] overflow-hidden stagger-item"
      :class="{ 'stagger-animate': animated }"
      style="--stagger-delay: 3"
    >
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

<style scoped>
.stagger-item {
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1),
              transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
  transition-delay: calc(var(--stagger-delay) * 0.1s);
}

.stagger-item.stagger-animate {
  opacity: 1;
  transform: translateY(0);
}
</style>
