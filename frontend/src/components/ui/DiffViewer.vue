<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  oldContent?: string
  newContent?: string
  filePath?: string
  diffText?: string
}

const props = defineProps<Props>()

interface DiffLine {
  type: 'add' | 'remove' | 'context' | 'header'
  content: string
  lineNumber?: number
}

const parsedDiff = computed<DiffLine[]>(() => {
  if (props.diffText) {
    return parseDiffText(props.diffText)
  }
  if (props.oldContent !== undefined && props.newContent !== undefined) {
    return computeDiff(props.oldContent, props.newContent)
  }
  return []
})

function parseDiffText(diff: string): DiffLine[] {
  const lines: DiffLine[] = []
  let lineNum = 0

  for (const line of diff.split('\n')) {
    if (line.startsWith('@@')) {
      lines.push({ type: 'header', content: line })
      // Parse line number from @@ -1,3 +1,4 @@
      const match = line.match(/@@ -\d+(?:,\d+)? \+(\d+)/)
      if (match && match[1]) lineNum = parseInt(match[1]) - 1
    } else if (line.startsWith('+') && !line.startsWith('+++')) {
      lineNum++
      lines.push({ type: 'add', content: line.slice(1), lineNumber: lineNum })
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      lines.push({ type: 'remove', content: line.slice(1) })
    } else if (line.startsWith(' ')) {
      lineNum++
      lines.push({ type: 'context', content: line.slice(1), lineNumber: lineNum })
    } else if (!line.startsWith('diff ') && !line.startsWith('index ') &&
               !line.startsWith('---') && !line.startsWith('+++')) {
      lineNum++
      lines.push({ type: 'context', content: line, lineNumber: lineNum })
    }
  }

  return lines
}

function computeDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split('\n')
  const newLines = newText.split('\n')
  const result: DiffLine[] = []

  // Simple line-by-line diff
  const maxLen = Math.max(oldLines.length, newLines.length)
  let lineNum = 0

  for (let i = 0; i < maxLen; i++) {
    const oldLine = oldLines[i]
    const newLine = newLines[i]

    if (oldLine === undefined) {
      lineNum++
      result.push({ type: 'add', content: newLine ?? '', lineNumber: lineNum })
    } else if (newLine === undefined) {
      result.push({ type: 'remove', content: oldLine })
    } else if (oldLine !== newLine) {
      result.push({ type: 'remove', content: oldLine })
      lineNum++
      result.push({ type: 'add', content: newLine, lineNumber: lineNum })
    } else {
      lineNum++
      result.push({ type: 'context', content: newLine, lineNumber: lineNum })
    }
  }

  return result
}
</script>

<template>
  <div class="diff-viewer">
    <div v-if="filePath" class="diff-header">
      <span class="file-icon">📄</span>
      <span class="file-path">{{ filePath }}</span>
    </div>
    <div class="diff-content">
      <div
        v-for="(line, i) in parsedDiff"
        :key="i"
        :class="['diff-line', `diff-${line.type}`]"
      >
        <span v-if="line.type !== 'header'" class="line-number">
          {{ line.lineNumber || '' }}
        </span>
        <span class="line-prefix">
          {{ line.type === 'add' ? '+' : line.type === 'remove' ? '-' : line.type === 'header' ? '' : ' ' }}
        </span>
        <span class="line-content">{{ line.content }}</span>
      </div>
      <div v-if="parsedDiff.length === 0" class="no-changes">
        No changes
      </div>
    </div>
  </div>
</template>

<style scoped>
.diff-viewer {
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Fira Code', 'Monaco', 'Menlo', monospace;
  font-size: 12px;
  background: var(--color-bg-dark, #1e1e1e);
}

.diff-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-secondary, #2d2d2d);
  border-bottom: 1px solid var(--color-border-dark, #404040);
}

.file-icon {
  font-size: 14px;
}

.file-path {
  color: var(--color-text-light, #e0e0e0);
  font-size: 11px;
}

.diff-content {
  padding: 8px 0;
  overflow-x: auto;
}

.diff-line {
  display: flex;
  align-items: flex-start;
  min-height: 20px;
  padding: 0 12px;
}

.diff-add {
  background: rgba(34, 197, 94, 0.15);
}

.diff-add .line-prefix,
.diff-add .line-content {
  color: #4ade80;
}

.diff-remove {
  background: rgba(239, 68, 68, 0.15);
}

.diff-remove .line-prefix,
.diff-remove .line-content {
  color: #f87171;
}

.diff-context .line-prefix,
.diff-context .line-content {
  color: var(--color-text-muted, #888);
}

.diff-header {
  background: rgba(99, 102, 241, 0.15);
}

.diff-header .line-content {
  color: #818cf8;
  font-weight: 500;
}

.line-number {
  width: 40px;
  text-align: right;
  padding-right: 12px;
  color: var(--color-text-muted, #666);
  user-select: none;
}

.line-prefix {
  width: 16px;
  text-align: center;
  user-select: none;
}

.line-content {
  flex: 1;
  white-space: pre;
}

.no-changes {
  padding: 24px;
  text-align: center;
  color: var(--color-text-muted, #666);
}
</style>
