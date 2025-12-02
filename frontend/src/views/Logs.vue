<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'
import { useLogsWebSocket } from '@/composables/useWebSocket'

const store = useAgentStore()
const { logs, wsConnected } = storeToRefs(store)

// Connect to WebSocket
useLogsWebSocket()

const containerRef = ref<HTMLElement | null>(null)
const autoScroll = ref(true)
const searchQuery = ref('')
const showSearch = ref(false)

// Parse ANSI codes
function parseAnsi(text: string): string {
  const ansiMap: Record<string, string> = {
    '30': 'ansi-black', '31': 'ansi-red', '32': 'ansi-green', '33': 'ansi-yellow',
    '34': 'ansi-blue', '35': 'ansi-magenta', '36': 'ansi-cyan', '37': 'ansi-white',
    '90': 'ansi-bright-black', '91': 'ansi-bright-red', '92': 'ansi-bright-green', '93': 'ansi-bright-yellow',
    '94': 'ansi-bright-blue', '95': 'ansi-bright-magenta', '96': 'ansi-bright-cyan', '97': 'ansi-bright-white',
    '1': 'ansi-bold', '2': 'ansi-dim', '3': 'ansi-italic', '4': 'ansi-underline',
    '38;5;208': 'text-[var(--color-accent)]', // Orange accent
  }

  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  escaped = escaped.replace(/\x1b\[([0-9;]+)m/g, (_, codes) => {
    if (codes === '0' || codes === '') return '</span>'
    const classes = codes.split(';').map((c: string) => ansiMap[c]).filter(Boolean).join(' ')
    return classes ? `<span class="${classes}">` : ''
  })

  return escaped
}

const filteredLines = computed(() => {
  const allLines = logs.value.split('\n')
  if (!searchQuery.value.trim()) return allLines
  const query = searchQuery.value.toLowerCase()
  return allLines.filter(line => line.toLowerCase().includes(query))
})

// Auto-scroll when content changes
watch(logs, async () => {
  if (autoScroll.value && containerRef.value) {
    await nextTick()
    containerRef.value.scrollTop = containerRef.value.scrollHeight
  }
})

function handleScroll() {
  if (!containerRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = containerRef.value
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 50
}

function scrollToBottom() {
  if (containerRef.value) {
    containerRef.value.scrollTop = containerRef.value.scrollHeight
    autoScroll.value = true
  }
}

function downloadLogs() {
  const blob = new Blob([logs.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `arche-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-4">
        <h1 class="text-xl font-mono text-[var(--color-text)]">Logs</h1>
        <div class="flex items-center gap-2">
          <span
            class="w-2 h-2 rounded-full"
            :class="wsConnected ? 'bg-[var(--color-success)]' : 'bg-[var(--color-error)]'"
          />
          <span class="text-xs text-[var(--color-text-muted)]">
            {{ wsConnected ? 'Live' : 'Disconnected' }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- Search toggle -->
        <button
          @click="showSearch = !showSearch"
          class="px-3 py-1.5 text-xs font-mono rounded border transition-colors"
          :class="showSearch
            ? 'bg-[var(--color-accent)] text-[var(--color-bg)] border-[var(--color-accent)]'
            : 'bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] border-[var(--color-border)] hover:text-[var(--color-text)]'"
        >
          Search
        </button>
        <!-- Auto-scroll indicator -->
        <button
          @click="scrollToBottom"
          class="px-3 py-1.5 text-xs font-mono rounded border transition-colors"
          :class="autoScroll
            ? 'bg-[var(--color-bg-elevated)] text-[var(--color-success)] border-[var(--color-border)]'
            : 'bg-[var(--color-warning)] text-[var(--color-bg)] border-[var(--color-warning)]'"
        >
          {{ autoScroll ? '↓ Auto' : '↓ Resume' }}
        </button>
        <!-- Download -->
        <button
          @click="downloadLogs"
          class="px-3 py-1.5 text-xs font-mono rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] border border-[var(--color-border)] hover:text-[var(--color-text)] transition-colors"
        >
          Download
        </button>
      </div>
    </div>

    <!-- Search bar -->
    <div v-if="showSearch" class="mb-4">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Filter logs..."
        class="w-full px-4 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded font-mono text-sm text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none"
      />
      <div v-if="searchQuery" class="mt-1 text-xs text-[var(--color-text-muted)]">
        {{ filteredLines.length }} lines matching
      </div>
    </div>

    <!-- Log container -->
    <div
      ref="containerRef"
      @scroll="handleScroll"
      class="flex-1 overflow-auto bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] p-4"
    >
      <pre
        class="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-[var(--color-text)]"
      ><template v-for="(line, i) in filteredLines" :key="i"><span v-html="parseAnsi(line)"></span>
</template></pre>
    </div>
  </div>
</template>
