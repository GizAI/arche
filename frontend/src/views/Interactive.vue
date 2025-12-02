<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useInteractiveStore } from '@/stores/interactive'
import SessionList from '@/components/ui/SessionList.vue'
import InteractiveConsole from '@/components/ui/InteractiveConsole.vue'
import PermissionModal from '@/components/ui/PermissionModal.vue'

const store = useInteractiveStore()
const {
  sessions,
  existingSessions,
  models,
  defaultModel,
  activeSessionId,
  activeSession,
  streamingText,
  streamingThinking,
  loading,
  error,
  pendingPermission,
  messages,
} = storeToRefs(store)

const showNewSessionModal = ref(false)
const newSessionName = ref('')
const newSessionModel = ref('')
const newSessionPermissionMode = ref('default')
const sidebarCollapsed = ref(false)
const isMobile = ref(window.innerWidth < 768)

// Permission modes with short labels for status bar
const permissionModes = [
  { value: 'default', label: 'Default (Ask for dangerous tools)', short: 'Default' },
  { value: 'plan', label: 'Plan Mode (Read-only)', short: 'Plan' },
  { value: 'acceptEdits', label: 'Accept Edits (Auto-approve file changes)', short: 'AcceptEdits' },
  { value: 'bypassPermissions', label: 'Bypass All (No confirmations)', short: 'YOLO' },
]

// Dynamic model list computed
const availableModels = computed(() => {
  if (models.value.length > 0) {
    return models.value.map(m => ({ value: m.id, label: m.name, recommended: m.recommended }))
  }
  // Fallback
  return [
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', recommended: true },
    { value: 'claude-opus-4-20250514', label: 'Claude Opus 4', recommended: false },
  ]
})

// Get current permission mode short label
const currentPermissionModeLabel = computed(() => {
  const mode = permissionModes.find(p => p.value === activeSession.value?.permission_mode)
  return mode?.short || 'Default'
})

// Cycle permission mode
function cyclePermissionMode() {
  if (!activeSession.value) return
  const currentIdx = permissionModes.findIndex(p => p.value === activeSession.value?.permission_mode)
  const nextIdx = (currentIdx + 1) % permissionModes.length
  const nextMode = permissionModes[nextIdx]!.value
  store.updateSession(activeSession.value.id, { permission_mode: nextMode })
}

// Responsive handling
function handleResize() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    sidebarCollapsed.value = true
  }
}

// Global keyboard shortcuts
function handleGlobalKeydown(e: KeyboardEvent) {
  // Shift+Tab: Cycle permission mode
  if (e.shiftKey && e.key === 'Tab') {
    e.preventDefault()
    cyclePermissionMode()
    return
  }

  // Ctrl+C or Escape: Interrupt if processing
  if ((e.ctrlKey && e.key === 'c') || e.key === 'Escape') {
    if (activeSession.value && ['thinking', 'tool_executing'].includes(activeSession.value.state)) {
      e.preventDefault()
      store.interrupt()
    }
  }
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleGlobalKeydown)

  // Fetch models first
  await store.fetchModels()
  // Set default model
  newSessionModel.value = defaultModel.value

  // Fetch sessions (includes existing sessions)
  await store.fetchSessions()
  store.connectGlobalWs()

  // Auto-select first session if available
  if (sessions.value.length > 0 && !activeSessionId.value) {
    await store.selectSession(sessions.value[0]!.id)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', handleGlobalKeydown)
  store.cleanup()
})

// Auto-collapse sidebar on mobile when session selected
watch(activeSessionId, (newId) => {
  if (newId && isMobile.value) {
    sidebarCollapsed.value = true
  }
})

async function handleCreateSession() {
  showNewSessionModal.value = true
}

async function confirmCreateSession() {
  try {
    const session = await store.createSession({
      name: newSessionName.value || undefined,
      model: newSessionModel.value,
      permission_mode: newSessionPermissionMode.value,
    })
    await store.selectSession(session.id)
    showNewSessionModal.value = false
    newSessionName.value = ''
  } catch {
    // Error is handled in store
  }
}

async function handleDeleteSession(sessionId: string) {
  await store.deleteSession(sessionId)
}

async function handleSelectSession(sessionId: string) {
  await store.selectSession(sessionId)
}

async function handleResumeSession(sessionId: string, projectName: string) {
  try {
    const session = await store.createSession({
      name: `Resume: ${projectName}`,
      model: defaultModel.value,
      permission_mode: newSessionPermissionMode.value,
      resume: sessionId,
    })
    await store.selectSession(session.id)
  } catch {
    // Error handled in store
  }
}

async function handleSendMessage(content: string) {
  await store.sendMessage(content)
}

async function handleInterrupt() {
  await store.interrupt()
}

async function handlePermissionResponse(allow: boolean, reason?: string, modifiedInput?: Record<string, any>) {
  await store.respondToPermission(allow, reason, modifiedInput)
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <div class="interactive-view">
    <!-- Sidebar Toggle (Mobile) -->
    <button
      class="sidebar-toggle"
      :class="{ collapsed: sidebarCollapsed }"
      @click="toggleSidebar"
    >
      <span class="toggle-icon">{{ sidebarCollapsed ? '&#9776;' : '&times;' }}</span>
    </button>

    <!-- Session Sidebar -->
    <aside
      class="session-sidebar"
      :class="{ collapsed: sidebarCollapsed }"
    >
      <SessionList
        :sessions="sessions"
        :existing-sessions="existingSessions"
        :active-session-id="activeSessionId"
        :loading="loading"
        @select="handleSelectSession"
        @create="handleCreateSession"
        @delete="handleDeleteSession"
        @resume="handleResumeSession"
      />
    </aside>

    <!-- Overlay for mobile -->
    <div
      v-if="!sidebarCollapsed && isMobile"
      class="sidebar-overlay"
      @click="sidebarCollapsed = true"
    ></div>

    <!-- Main Content -->
    <main class="main-content">
      <!-- Active Session Console -->
      <InteractiveConsole
        v-if="activeSession"
        :messages="messages"
        :streaming-text="streamingText"
        :streaming-thinking="streamingThinking"
        :session-state="activeSession.state"
        :session-name="activeSession.name"
        :model="activeSession.model"
        :total-cost="activeSession.total_cost_usd"
        @send="handleSendMessage"
        @interrupt="handleInterrupt"
      />

      <!-- Empty State -->
      <div v-else class="empty-state">
        <div class="empty-content">
          <div class="empty-icon">&#128172;</div>
          <h2>Interactive Mode</h2>
          <p>Chat with Claude directly, with full tool access and human-in-the-loop controls.</p>
          <button class="create-session-btn" @click="handleCreateSession">
            Start New Session
          </button>
        </div>
      </div>
    </main>

    <!-- Permission Modal -->
    <PermissionModal
      :request="pendingPermission"
      @respond="handlePermissionResponse"
    />

    <!-- New Session Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showNewSessionModal" class="modal-overlay" @click.self="showNewSessionModal = false">
          <div class="new-session-modal">
            <h2>New Session</h2>

            <div class="form-group">
              <label>Session Name (optional)</label>
              <input
                v-model="newSessionName"
                type="text"
                placeholder="e.g., Feature Development"
                @keyup.enter="confirmCreateSession"
              />
            </div>

            <div class="form-group">
              <label>Model</label>
              <select v-model="newSessionModel">
                <option v-for="m in availableModels" :key="m.value" :value="m.value">
                  {{ m.label }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label>Permission Mode</label>
              <select v-model="newSessionPermissionMode">
                <option v-for="p in permissionModes" :key="p.value" :value="p.value">
                  {{ p.label }}
                </option>
              </select>
            </div>

            <div class="modal-actions">
              <button class="btn-cancel" @click="showNewSessionModal = false">
                Cancel
              </button>
              <button class="btn-create" @click="confirmCreateSession" :disabled="loading">
                Create Session
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Permission Mode Indicator (Bottom Left) -->
    <div v-if="activeSession" class="permission-indicator" @click="cyclePermissionMode">
      <span class="permission-label">{{ currentPermissionModeLabel }}</span>
      <span class="permission-hint">shift+tab</span>
    </div>

    <!-- Error Toast -->
    <Transition name="toast">
      <div v-if="error" class="error-toast">
        <span>{{ error }}</span>
        <button @click="store.error = null">&times;</button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.interactive-view {
  display: flex;
  height: 100%;
  position: relative;
  background: var(--color-bg);
}

.sidebar-toggle {
  display: none;
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 100;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
  color: var(--color-text);
  font-size: 1.25rem;
  cursor: pointer;
  align-items: center;
  justify-content: center;
}

@media (max-width: 768px) {
  .sidebar-toggle {
    display: flex;
  }
}

.session-sidebar {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid var(--color-border);
  transition: transform 0.2s ease, width 0.2s ease, min-width 0.2s ease;
}

@media (max-width: 768px) {
  .session-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 90;
    width: 280px;
    background: var(--color-bg);
  }

  .session-sidebar.collapsed {
    transform: translateX(-100%);
  }
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 80;
}

.main-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

@media (max-width: 768px) {
  .main-content {
    padding-top: 60px;
  }
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.empty-content {
  text-align: center;
  max-width: 400px;
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-content h2 {
  margin: 0 0 0.5rem;
  font-size: 1.5rem;
}

.empty-content p {
  margin: 0 0 1.5rem;
  color: var(--color-text-muted);
  line-height: 1.6;
}

.create-session-btn {
  padding: 0.875rem 2rem;
  border-radius: 8px;
  border: none;
  background: var(--color-accent);
  color: var(--color-bg);
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease;
}

.create-session-btn:hover {
  background: var(--color-accent-muted);
}

/* New Session Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.new-session-modal {
  background: var(--color-bg);
  border-radius: 16px;
  width: 100%;
  max-width: 420px;
  padding: 1.5rem;
  border: 1px solid var(--color-border);
}

.new-session-modal h2 {
  margin: 0 0 1.5rem;
  font-size: 1.25rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-muted);
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
  color: var(--color-text);
  font-size: 0.9375rem;
  outline: none;
  transition: border-color 0.15s ease;
}

.form-group input:focus,
.form-group select:focus {
  border-color: var(--color-accent);
}

.modal-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.btn-cancel,
.btn-create {
  flex: 1;
  padding: 0.75rem;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel {
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  color: var(--color-text);
}

.btn-cancel:hover {
  background: var(--color-bg-elevated);
}

.btn-create {
  background: var(--color-accent);
  border: none;
  color: var(--color-bg);
}

.btn-create:hover:not(:disabled) {
  background: var(--color-accent-muted);
}

.btn-create:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error Toast */
.error-toast {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-error);
  color: white;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 1100;
}

.error-toast button {
  background: none;
  border: none;
  color: white;
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: all 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .new-session-modal,
.modal-leave-to .new-session-modal {
  transform: scale(0.95);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 20px);
}

/* Permission Mode Indicator */
.permission-indicator {
  position: fixed;
  bottom: 1rem;
  left: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  cursor: pointer;
  z-index: 50;
  transition: all 0.15s ease;
}

.permission-indicator:hover {
  background: var(--color-bg-muted);
  border-color: var(--color-accent);
}

.permission-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text);
}

.permission-hint {
  font-size: 0.625rem;
  color: var(--color-text-subtle);
  padding: 0.125rem 0.25rem;
  border-radius: 3px;
  background: var(--color-bg-muted);
}

@media (max-width: 768px) {
  .permission-indicator {
    bottom: 5rem;
    left: 0.5rem;
    padding: 0.375rem 0.5rem;
  }

  .permission-hint {
    display: none;
  }
}
</style>
