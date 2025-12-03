<script setup lang="ts">
import { computed } from 'vue'
import type { FileOperation } from '@/stores/interactive'

const props = defineProps<{
  operation: FileOperation | null
}>()

const emit = defineEmits<{
  approve: [opId: string]
  reject: [opId: string, reason?: string]
  close: []
}>()

const operationIcon = computed(() => {
  if (!props.operation) return ''
  switch (props.operation.operation) {
    case 'write_file': return '📝'
    case 'edit_file': return '✏️'
    case 'read_file': return '📖'
    case 'execute': return '⚡'
    case 'glob': return '🔍'
    case 'grep': return '🔎'
    default: return '📁'
  }
})

const operationLabel = computed(() => {
  if (!props.operation) return ''
  switch (props.operation.operation) {
    case 'write_file': return 'Write File'
    case 'edit_file': return 'Edit File'
    case 'read_file': return 'Read File'
    case 'execute': return 'Execute Command'
    case 'glob': return 'Search Files'
    case 'grep': return 'Search Content'
    default: return props.operation.operation
  }
})

function handleApprove() {
  if (props.operation) {
    emit('approve', props.operation.id)
  }
}

function handleReject() {
  if (props.operation) {
    emit('reject', props.operation.id)
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="operation && !operation.approved" class="modal-overlay" @click.self="emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <span class="op-icon">{{ operationIcon }}</span>
          <h3 class="modal-title">{{ operationLabel }}</h3>
          <button class="close-btn" @click="emit('close')">×</button>
        </div>

        <div class="modal-body">
          <div class="op-detail">
            <span class="detail-label">Path:</span>
            <code class="detail-value">{{ operation.path }}</code>
          </div>

          <div v-if="operation.content_preview" class="op-preview">
            <span class="preview-label">Preview:</span>
            <pre class="preview-content">{{ operation.content_preview }}</pre>
          </div>

          <div v-if="operation.diff" class="op-diff">
            <span class="diff-label">Changes:</span>
            <pre class="diff-content">{{ operation.diff }}</pre>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-reject" @click="handleReject">
            Reject
          </button>
          <button class="btn btn-approve" @click="handleApprove">
            Approve
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  z-index: 1000;
}

.modal-content {
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: var(--bg-color, #1a1a1a);
  border: 1px solid var(--border-color, #333);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-color, #333);
}

.op-icon {
  font-size: 1.5rem;
}

.modal-title {
  flex: 1;
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-color, #e0e0e0);
}

.close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted, #666);
  font-size: 1.5rem;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.close-btn:hover {
  background: var(--bg-hover, #252525);
  color: var(--text-color, #e0e0e0);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.25rem;
}

.op-detail {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.detail-label {
  flex-shrink: 0;
  color: var(--text-muted, #666);
  font-size: 0.875rem;
}

.detail-value {
  flex: 1;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background: var(--bg-secondary, #252525);
  color: var(--accent-color, #5a67d8);
  font-size: 0.875rem;
  word-break: break-all;
}

.op-preview, .op-diff {
  margin-top: 1rem;
}

.preview-label, .diff-label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-muted, #666);
  font-size: 0.875rem;
}

.preview-content, .diff-content {
  margin: 0;
  padding: 1rem;
  border-radius: 8px;
  background: var(--bg-secondary, #252525);
  color: var(--text-color, #e0e0e0);
  font-size: 0.75rem;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border-color, #333);
}

.btn {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
}

.btn-reject {
  background: var(--bg-secondary, #252525);
  color: var(--text-color, #e0e0e0);
}

.btn-reject:hover {
  background: var(--error-bg, rgba(239, 68, 68, 0.2));
  color: var(--error-color, #ef4444);
}

.btn-approve {
  background: var(--success-color, #10b981);
  color: white;
}

.btn-approve:hover {
  opacity: 0.9;
}
</style>
