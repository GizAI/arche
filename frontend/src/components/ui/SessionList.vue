<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Session, SessionState, ExistingSession } from '@/stores/interactive'

const props = defineProps<{
  sessions: Session[]
  existingSessions?: ExistingSession[]
  activeSessionId: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [sessionId: string]
  create: []
  delete: [sessionId: string]
  resume: [sessionId: string, projectName: string]
}>()

const showExisting = ref(false)

const sortedSessions = computed(() => {
  return [...props.sessions].sort((a, b) => {
    // Active sessions first
    const aActive = isActiveState(a.state)
    const bActive = isActiveState(b.state)
    if (aActive && !bActive) return -1
    if (!aActive && bActive) return 1
    // Then by updated_at descending
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })
})

function isActiveState(state: SessionState): boolean {
  return ['thinking', 'tool_executing', 'permission_pending'].includes(state)
}

function getStateColor(state: SessionState): string {
  switch (state) {
    case 'thinking':
      return 'var(--color-accent)'
    case 'tool_executing':
      return 'var(--color-info)'
    case 'permission_pending':
      return 'var(--color-warning)'
    case 'completed':
      return 'var(--color-success)'
    case 'error':
      return 'var(--color-error)'
    case 'interrupted':
      return 'var(--color-text-muted)'
    default:
      return 'var(--color-text-subtle)'
  }
}

function getStateLabel(state: SessionState): string {
  switch (state) {
    case 'idle':
      return 'Idle'
    case 'thinking':
      return 'Thinking...'
    case 'tool_executing':
      return 'Executing'
    case 'permission_pending':
      return 'Awaiting'
    case 'completed':
      return 'Done'
    case 'error':
      return 'Error'
    case 'interrupted':
      return 'Stopped'
    default:
      return state
  }
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return 'Just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return date.toLocaleDateString()
}

function handleDelete(e: Event, sessionId: string) {
  e.stopPropagation()
  if (confirm('Delete this session?')) {
    emit('delete', sessionId)
  }
}

function handleResume(existing: ExistingSession) {
  emit('resume', existing.session_id, getProjectName(existing.project_path))
}

function formatExistingTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return 'Just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`
  return date.toLocaleDateString()
}

function getProjectName(projectPath: string): string {
  // Convert /home/user/arche -> arche
  const parts = projectPath.split('/')
  return parts[parts.length - 1] || projectPath
}

const sortedExistingSessions = computed(() => {
  if (!props.existingSessions) return []
  return [...props.existingSessions].sort((a, b) => {
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })
})
</script>

<template>
  <div class="session-list">
    <div class="session-list-header">
      <h3>Sessions</h3>
      <button
        class="create-btn"
        @click="emit('create')"
        :disabled="loading"
        title="New Session"
      >
        <span class="icon">+</span>
      </button>
    </div>

    <div class="session-items" v-if="sortedSessions.length > 0">
      <div
        v-for="session in sortedSessions"
        :key="session.id"
        class="session-item"
        :class="{
          active: session.id === activeSessionId,
          processing: isActiveState(session.state)
        }"
        @click="emit('select', session.id)"
      >
        <div class="session-main">
          <div class="session-name">{{ session.name }}</div>
          <div class="session-meta">
            <span class="session-model">{{ session.model.split('-').slice(-2, -1)[0] || 'claude' }}</span>
            <span class="session-messages">{{ session.message_count }} msgs</span>
          </div>
        </div>

        <div class="session-status">
          <div
            class="status-indicator"
            :class="{ pulsing: isActiveState(session.state) }"
            :style="{ backgroundColor: getStateColor(session.state) }"
            :title="getStateLabel(session.state)"
          ></div>
          <span class="status-label">{{ getStateLabel(session.state) }}</span>
        </div>

        <div class="session-actions">
          <button
            class="delete-btn"
            @click="(e) => handleDelete(e, session.id)"
            title="Delete"
          >
            &times;
          </button>
        </div>

        <div class="session-time">
          {{ formatTime(session.updated_at) }}
        </div>
      </div>
    </div>

    <div class="empty-state" v-else-if="!sortedExistingSessions.length">
      <p>No sessions yet</p>
      <button class="create-btn-large" @click="emit('create')">
        Create New Session
      </button>
    </div>

    <!-- Existing Sessions (Resumable) -->
    <div v-if="sortedExistingSessions.length > 0" class="existing-sessions">
      <button class="section-toggle" @click="showExisting = !showExisting">
        <span class="toggle-icon">{{ showExisting ? '▼' : '▶' }}</span>
        <span class="section-title">Resume Previous</span>
        <span class="section-count">{{ sortedExistingSessions.length }}</span>
      </button>

      <div v-if="showExisting" class="existing-items">
        <div
          v-for="existing in sortedExistingSessions"
          :key="existing.session_id"
          class="existing-item"
          @click="handleResume(existing)"
        >
          <div class="existing-main">
            <div class="existing-project">{{ getProjectName(existing.project_path) }}</div>
            <div class="existing-meta">
              <span v-if="existing.git_branch" class="existing-branch">
                {{ existing.git_branch }}
              </span>
              <span class="existing-msgs">{{ existing.message_count }} msgs</span>
              <span class="existing-time">{{ formatExistingTime(existing.updated_at) }}</span>
            </div>
            <div v-if="existing.first_message_preview" class="existing-preview">
              {{ existing.first_message_preview }}
            </div>
          </div>
          <div class="existing-action">
            <span class="resume-icon">↻</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg);
}

.session-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.session-list-header h3 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.create-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
  color: var(--color-text);
  font-size: 1.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.create-btn:hover:not(:disabled) {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: var(--color-bg);
}

.create-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.session-items {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.session-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  grid-template-rows: auto auto;
  gap: 0.25rem 0.75rem;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  border-radius: 8px;
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
}

.session-item:hover {
  background: var(--color-bg-muted);
  border-color: var(--color-border);
}

.session-item.active {
  background: var(--color-bg-elevated);
  border-color: var(--color-accent);
}

.session-item.processing {
  animation: subtle-pulse 2s ease-in-out infinite;
}

@keyframes subtle-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

.session-main {
  grid-column: 1;
  grid-row: 1;
  min-width: 0;
}

.session-name {
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-subtle);
  margin-top: 0.25rem;
}

.session-model {
  text-transform: capitalize;
}

.session-status {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-indicator.pulsing {
  animation: pulse-glow 1.5s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% {
    box-shadow: 0 0 0 0 currentColor;
    opacity: 1;
  }
  50% {
    box-shadow: 0 0 8px 2px currentColor;
    opacity: 0.8;
  }
}

.status-label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.session-actions {
  grid-column: 3;
  grid-row: 1;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.session-item:hover .session-actions {
  opacity: 1;
}

.delete-btn {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--color-text-subtle);
  font-size: 1.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.delete-btn:hover {
  background: var(--color-error);
  color: white;
}

.session-time {
  grid-column: 1 / -1;
  grid-row: 2;
  font-size: 0.675rem;
  color: var(--color-text-subtle);
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
  color: var(--color-text-muted);
}

.empty-state p {
  margin-bottom: 1rem;
}

.create-btn-large {
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  border: 1px solid var(--color-accent);
  background: transparent;
  color: var(--color-accent);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.create-btn-large:hover {
  background: var(--color-accent);
  color: var(--color-bg);
}

/* Existing Sessions */
.existing-sessions {
  border-top: 1px solid var(--color-border);
  padding: 0.5rem;
}

.section-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 0.75rem;
  cursor: pointer;
  text-align: left;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.section-toggle:hover {
  background: var(--color-bg-muted);
}

.toggle-icon {
  font-size: 0.625rem;
  width: 1rem;
}

.section-title {
  flex: 1;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}

.section-count {
  background: var(--color-bg-muted);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.675rem;
}

.existing-items {
  margin-top: 0.25rem;
}

.existing-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  border-radius: 8px;
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
}

.existing-item:hover {
  background: var(--color-bg-muted);
  border-color: var(--color-border);
}

.existing-main {
  flex: 1;
  min-width: 0;
}

.existing-project {
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.existing-meta {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-subtle);
  margin-top: 0.25rem;
}

.existing-branch {
  color: var(--color-info);
}

.existing-preview {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin-top: 0.375rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.existing-action {
  flex-shrink: 0;
}

.resume-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 1rem;
  color: var(--color-text-subtle);
  transition: color 0.15s ease;
}

.existing-item:hover .resume-icon {
  color: var(--color-accent);
}
</style>
