<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'

interface Props {
  output: string[] | string
  maxHeight?: number
  autoScroll?: boolean
  showCopy?: boolean
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  maxHeight: 300,
  autoScroll: true,
  showCopy: true,
})

const contentRef = ref<HTMLElement | null>(null)
const copied = ref(false)

const lines = computed(() => {
  if (typeof props.output === 'string') {
    return props.output.split('\n')
  }
  return props.output
})

const fullText = computed(() => lines.value.join('\n'))

// ANSI color code to CSS mapping
const ansiColors: Record<number, string> = {
  30: '#000', 31: '#e74c3c', 32: '#2ecc71', 33: '#f39c12',
  34: '#3498db', 35: '#9b59b6', 36: '#1abc9c', 37: '#ecf0f1',
  90: '#7f8c8d', 91: '#e74c3c', 92: '#2ecc71', 93: '#f1c40f',
  94: '#3498db', 95: '#9b59b6', 96: '#1abc9c', 97: '#fff',
}

function parseAnsi(text: string): { html: string } {
  let html = text
    // Escape HTML
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Replace ANSI codes with spans
  html = html.replace(/\x1b\[(\d+(?:;\d+)*)m/g, (_, codes) => {
    const codeList = codes.split(';').map(Number)
    const styles: string[] = []

    for (const code of codeList) {
      if (code === 0) return '</span>'
      if (code === 1) styles.push('font-weight:bold')
      if (code === 3) styles.push('font-style:italic')
      if (code === 4) styles.push('text-decoration:underline')
      if (ansiColors[code]) styles.push(`color:${ansiColors[code]}`)
      if (code >= 40 && code <= 47) {
        styles.push(`background:${ansiColors[code - 10]}`)
      }
    }

    return styles.length ? `<span style="${styles.join(';')}">` : ''
  })

  // Remove any remaining ANSI codes
  html = html.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')

  return { html }
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(fullText.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

function scrollToBottom() {
  if (props.autoScroll && contentRef.value) {
    contentRef.value.scrollTop = contentRef.value.scrollHeight
  }
}

watch(lines, async () => {
  await nextTick()
  scrollToBottom()
})

onMounted(() => {
  scrollToBottom()
})
</script>

<template>
  <div class="terminal-output">
    <div v-if="title || showCopy" class="terminal-header">
      <span v-if="title" class="terminal-title">{{ title }}</span>
      <button v-if="showCopy" class="copy-btn" @click="copyToClipboard">
        {{ copied ? 'Copied!' : 'Copy' }}
      </button>
    </div>
    <div
      ref="contentRef"
      class="terminal-content"
      :style="{ maxHeight: `${maxHeight}px` }"
    >
      <div
        v-for="(line, i) in lines"
        :key="i"
        class="terminal-line"
        v-html="parseAnsi(line).html"
      ></div>
      <div v-if="lines.length === 0" class="empty-output">
        No output
      </div>
    </div>
  </div>
</template>

<style scoped>
.terminal-output {
  background: var(--color-bg-dark, #1e1e1e);
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Fira Code', 'Monaco', 'Menlo', monospace;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: var(--color-bg-secondary, #2d2d2d);
  border-bottom: 1px solid var(--color-border-dark, #404040);
}

.terminal-title {
  font-size: 11px;
  color: var(--color-text-muted, #888);
  font-weight: 500;
}

.copy-btn {
  padding: 2px 8px;
  font-size: 10px;
  background: transparent;
  border: 1px solid var(--color-border-dark, #404040);
  border-radius: 4px;
  color: var(--color-text-muted, #888);
  cursor: pointer;
  transition: all 0.15s ease;
}

.copy-btn:hover {
  background: var(--color-bg-hover, rgba(255, 255, 255, 0.1));
  color: var(--color-text-light, #fff);
}

.terminal-content {
  padding: 12px;
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-light, #e0e0e0);
}

.terminal-line {
  white-space: pre-wrap;
  word-break: break-all;
  min-height: 18px;
}

.terminal-line:empty::after {
  content: '\00a0';
}

.empty-output {
  color: var(--color-text-muted, #666);
  font-style: italic;
  text-align: center;
  padding: 12px;
}

/* Custom scrollbar */
.terminal-content::-webkit-scrollbar {
  width: 8px;
}

.terminal-content::-webkit-scrollbar-track {
  background: transparent;
}

.terminal-content::-webkit-scrollbar-thumb {
  background: var(--color-border-dark, #404040);
  border-radius: 4px;
}

.terminal-content::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-muted, #666);
}
</style>
