<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps<{
  content: string
  maxLines?: number
}>()

const containerRef = ref<HTMLElement | null>(null)
const autoScroll = ref(true)

const lines = computed(() => {
  const allLines = props.content.split('\n')
  const max = props.maxLines ?? 50
  return allLines.slice(-max)
})

// Parse ANSI codes for basic coloring
function parseAnsi(text: string): string {
  // Basic ANSI color codes mapping
  const ansiMap: Record<string, string> = {
    '30': 'ansi-black', '31': 'ansi-red', '32': 'ansi-green', '33': 'ansi-yellow',
    '34': 'ansi-blue', '35': 'ansi-magenta', '36': 'ansi-cyan', '37': 'ansi-white',
    '90': 'ansi-bright-black', '91': 'ansi-bright-red', '92': 'ansi-bright-green', '93': 'ansi-bright-yellow',
    '94': 'ansi-bright-blue', '95': 'ansi-bright-magenta', '96': 'ansi-bright-cyan', '97': 'ansi-bright-white',
    '1': 'ansi-bold', '2': 'ansi-dim', '3': 'ansi-italic', '4': 'ansi-underline',
  }

  // Escape HTML first
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Replace ANSI codes with spans
  escaped = escaped.replace(/\x1b\[([0-9;]+)m/g, (_, codes) => {
    if (codes === '0' || codes === '') return '</span>'
    const classes = codes.split(';').map((c: string) => ansiMap[c]).filter(Boolean).join(' ')
    return classes ? `<span class="${classes}">` : ''
  })

  return escaped
}

// Auto-scroll when content changes
watch(() => props.content, async () => {
  if (autoScroll.value && containerRef.value) {
    await nextTick()
    containerRef.value.scrollTop = containerRef.value.scrollHeight
  }
})

function handleScroll() {
  if (!containerRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = containerRef.value
  // If user scrolled up, disable auto-scroll
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 50
}
</script>

<template>
  <div
    ref="containerRef"
    @scroll="handleScroll"
    class="h-full overflow-auto p-4 font-mono text-xs leading-relaxed bg-[var(--color-bg)]"
  >
    <div v-if="!content" class="text-[var(--color-text-subtle)]">
      No logs yet...
    </div>
    <pre v-else class="whitespace-pre-wrap break-words text-[var(--color-text)]"><template v-for="(line, i) in lines" :key="i"><span v-html="parseAnsi(line)"></span>
</template></pre>
  </div>
</template>
