<script setup lang="ts">
import { ref, computed } from 'vue'
import DiffViewer from './DiffViewer.vue'
import TerminalOutput from './TerminalOutput.vue'

interface Props {
  toolName: string
  toolInput: Record<string, any>
  toolOutput?: any
  status?: 'pending' | 'executing' | 'completed' | 'error'
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  status: 'pending',
})

const isExpanded = ref(false)

const isEditTool = computed(() => props.toolName === 'Edit' || props.toolName === 'str_replace_editor')
const isBashTool = computed(() => props.toolName === 'Bash' || props.toolName === 'execute_command')
const isReadTool = computed(() => props.toolName === 'Read' || props.toolName === 'file_read')

const filePath = computed(() => {
  if (isEditTool.value) return props.toolInput.file_path || props.toolInput.path
  if (isReadTool.value) return props.toolInput.file_path || props.toolInput.path
  return null
})

const diffContent = computed(() => {
  if (!isEditTool.value) return null
  // Construct diff from old_string and new_string
  const old = props.toolInput.old_string || ''
  const newStr = props.toolInput.new_string || ''
  if (!old && !newStr) return null

  const lines: string[] = []
  lines.push(`--- a/${filePath.value || 'file'}`)
  lines.push(`+++ b/${filePath.value || 'file'}`)
  lines.push('@@ -1 +1 @@')

  for (const line of old.split('\n')) {
    lines.push(`-${line}`)
  }
  for (const line of newStr.split('\n')) {
    lines.push(`+${line}`)
  }

  return lines.join('\n')
})

const bashCommand = computed(() => {
  if (!isBashTool.value) return null
  return props.toolInput.command || ''
})

const bashOutput = computed(() => {
  if (!isBashTool.value || !props.toolOutput) return null
  if (typeof props.toolOutput === 'string') return props.toolOutput
  if (props.toolOutput.output) return props.toolOutput.output
  if (props.toolOutput.stdout) return props.toolOutput.stdout
  return JSON.stringify(props.toolOutput, null, 2)
})

function getStatusIcon(status: string) {
  switch (status) {
    case 'executing': return '⏳'
    case 'completed': return '✓'
    case 'error': return '✕'
    default: return '○'
  }
}

function getStatusColor(status: string) {
  switch (status) {
    case 'executing': return 'var(--color-primary, #4f46e5)'
    case 'completed': return 'var(--color-success, #22c55e)'
    case 'error': return 'var(--color-danger, #ef4444)'
    default: return 'var(--color-text-secondary, #666)'
  }
}

function getToolIcon(name: string) {
  if (name.includes('Bash') || name.includes('command')) return '💻'
  if (name.includes('Edit') || name.includes('replace')) return '✏️'
  if (name.includes('Read') || name.includes('read')) return '📖'
  if (name.includes('Write') || name.includes('write')) return '📝'
  if (name.includes('Glob') || name.includes('Search')) return '🔍'
  if (name.includes('Web')) return '🌐'
  return '🔧'
}
</script>

<template>
  <div class="tool-execution-viewer" :class="[`status-${status}`]">
    <div class="tool-header" @click="isExpanded = !isExpanded">
      <span class="tool-icon">{{ getToolIcon(toolName) }}</span>
      <span class="tool-name">{{ toolName }}</span>
      <span v-if="filePath" class="tool-file">{{ filePath }}</span>
      <span class="tool-status" :style="{ color: getStatusColor(status) }">
        {{ getStatusIcon(status) }}
      </span>
      <button class="expand-btn" :class="{ expanded: isExpanded }">
        ▶
      </button>
    </div>

    <div v-if="isExpanded" class="tool-details">
      <!-- Edit Tool: Show Diff -->
      <div v-if="isEditTool && diffContent" class="detail-section">
        <DiffViewer :diff-text="diffContent" :file-path="filePath || undefined" />
      </div>

      <!-- Bash Tool: Show Command and Output -->
      <div v-else-if="isBashTool" class="detail-section">
        <div class="bash-command">
          <span class="label">Command:</span>
          <code>{{ bashCommand }}</code>
        </div>
        <TerminalOutput
          v-if="bashOutput"
          :output="bashOutput"
          title="Output"
          :max-height="200"
        />
      </div>

      <!-- Generic: Show Input/Output JSON -->
      <div v-else class="detail-section">
        <div class="json-section">
          <div class="section-title">Input</div>
          <pre class="json-content">{{ JSON.stringify(toolInput, null, 2) }}</pre>
        </div>
        <div v-if="toolOutput" class="json-section">
          <div class="section-title">Output</div>
          <pre class="json-content">{{ typeof toolOutput === 'string' ? toolOutput : JSON.stringify(toolOutput, null, 2) }}</pre>
        </div>
      </div>

      <!-- Error Message -->
      <div v-if="error" class="error-message">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-execution-viewer {
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0;
}

.tool-execution-viewer.status-error {
  border-color: var(--color-danger, #ef4444);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-bg-secondary, #f5f5f5);
  cursor: pointer;
  user-select: none;
}

.tool-header:hover {
  background: var(--color-bg-hover, #eee);
}

.tool-icon {
  font-size: 14px;
}

.tool-name {
  font-weight: 600;
  font-size: 13px;
}

.tool-file {
  flex: 1;
  font-family: monospace;
  font-size: 11px;
  color: var(--color-text-secondary, #666);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-status {
  font-size: 14px;
}

.expand-btn {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  font-size: 10px;
  color: var(--color-text-secondary, #666);
  transition: transform 0.15s ease;
}

.expand-btn.expanded {
  transform: rotate(90deg);
}

.tool-details {
  padding: 12px;
  border-top: 1px solid var(--color-border, #e5e5e5);
}

.detail-section {
  margin-bottom: 12px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.bash-command {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}

.bash-command .label {
  color: var(--color-text-secondary, #666);
}

.bash-command code {
  flex: 1;
  padding: 4px 8px;
  background: var(--color-bg-dark, #1e1e1e);
  color: var(--color-text-light, #e0e0e0);
  border-radius: 4px;
  font-family: monospace;
  overflow-x: auto;
}

.json-section {
  margin-bottom: 12px;
}

.section-title {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary, #666);
  margin-bottom: 4px;
  text-transform: uppercase;
}

.json-content {
  background: var(--color-bg-dark, #1e1e1e);
  color: var(--color-text-light, #e0e0e0);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: monospace;
  font-size: 11px;
  overflow-x: auto;
  max-height: 150px;
  margin: 0;
}

.error-message {
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-danger, #ef4444);
  border-radius: 6px;
  font-size: 12px;
}
</style>
