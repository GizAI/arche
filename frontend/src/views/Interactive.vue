<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useInteractiveStore, type ThinkingMode, type EngineType } from '@/stores/interactive'
import SessionList from '@/components/ui/SessionList.vue'
import InteractiveConsole from '@/components/ui/InteractiveConsole.vue'
import PermissionModal from '@/components/ui/PermissionModal.vue'
import ThinkingModeSelector from '@/components/ui/ThinkingModeSelector.vue'
import PlanModePanel from '@/components/ui/PlanModePanel.vue'
import BackgroundTaskPanel from '@/components/ui/BackgroundTaskPanel.vue'
import CheckpointManager from '@/components/ui/CheckpointManager.vue'
import MCPServerPanel from '@/components/ui/MCPServerPanel.vue'
import CostTracker from '@/components/ui/CostTracker.vue'
import ShortcutsHelp from '@/components/ui/ShortcutsHelp.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

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
  // Extended
  backgroundTasks,
  checkpoints,
  mcpServers,
  usage,
  thinkingMode,
  planModeActive,
  runningTasks,
  connectedMcpServers,
  mcpToolCount,
  showBackgroundPanel,
  showCheckpointsPanel,
  showMcpPanel,
  sessionTodos,
  sessionFileOps,
  skills,
} = storeToRefs(store)

const showNewSessionModal = ref(false)
const newSessionName = ref('')
const newSessionModel = ref('')
const newSessionPermissionMode = ref('default')
const newSessionEngine = ref<EngineType>('claude_sdk')
const newSessionThinkingMode = ref<ThinkingMode>('normal')
const sidebarCollapsed = ref(false)
const isMobile = ref(window.innerWidth < 768)
const activeRightPanel = ref<'none' | 'background' | 'checkpoints' | 'mcp'>('none')

// Permission modes with short labels for status bar
const permissionModes = [
  { value: 'default', label: 'Default (Ask for dangerous tools)', short: 'Default' },
  { value: 'plan', label: 'Plan Mode (Read-only)', short: 'Plan' },
  { value: 'acceptEdits', label: 'Accept Edits (Auto-approve file changes)', short: 'AcceptEdits' },
  { value: 'bypassPermissions', label: 'Bypass All (No confirmations)', short: 'YOLO' },
]

const engines = [
  { value: 'claude_sdk', label: 'Claude SDK' },
  { value: 'deepagents', label: 'DeepAgents' },
]

const thinkingModes: { value: ThinkingMode; label: string }[] = [
  { value: 'normal', label: 'Normal' },
  { value: 'think', label: 'Think (10K)' },
  { value: 'think_hard', label: 'Think Hard (50K)' },
  { value: 'ultrathink', label: 'Ultrathink (100K)' },
]

// Dynamic model list computed
const availableModels = computed(() => {
  if (models.value.length > 0) {
    return models.value.map(m => ({ value: m.id, label: m.name, recommended: m.recommended }))
  }
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

// Status bar info
const statusInfo = computed(() => {
  if (!activeSession.value) return null
  return {
    model: activeSession.value.model.replace('claude-', '').replace('-20250514', ''),
    thinkingMode: thinkingMode.value,
    planMode: planModeActive.value,
    cost: activeSession.value.total_cost_usd,
    state: activeSession.value.state,
  }
})

// Cycle permission mode
function cyclePermissionMode() {
  if (!activeSession.value) return
  const currentIdx = permissionModes.findIndex(p => p.value === activeSession.value?.permission_mode)
  const nextIdx = (currentIdx + 1) % permissionModes.length
  const nextMode = permissionModes[nextIdx]!.value
  store.updateSession(activeSession.value.id, { permission_mode: nextMode })
}

// Toggle right panel
function toggleRightPanel(panel: 'background' | 'checkpoints' | 'mcp') {
  if (activeRightPanel.value === panel) {
    activeRightPanel.value = 'none'
  } else {
    activeRightPanel.value = panel
  }
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

// Initialize keyboard shortcuts
useKeyboardShortcuts()

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleGlobalKeydown)

  // Fetch models first
  await store.fetchModels()
  newSessionModel.value = defaultModel.value

  // Fetch sessions and initialize extended features
  await Promise.all([
    store.fetchSessions(),
    store.initializeExtended(),
  ])

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

// Sync panel visibility with store
watch(showBackgroundPanel, (v) => { if (v) activeRightPanel.value = 'background'; else if (activeRightPanel.value === 'background') activeRightPanel.value = 'none' })
watch(showCheckpointsPanel, (v) => { if (v) activeRightPanel.value = 'checkpoints'; else if (activeRightPanel.value === 'checkpoints') activeRightPanel.value = 'none' })
watch(showMcpPanel, (v) => { if (v) activeRightPanel.value = 'mcp'; else if (activeRightPanel.value === 'mcp') activeRightPanel.value = 'none' })
watch(activeRightPanel, (panel) => {
  store.showBackgroundPanel = panel === 'background'
  store.showCheckpointsPanel = panel === 'checkpoints'
  store.showMcpPanel = panel === 'mcp'
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
      engine: newSessionEngine.value,
      thinking_mode: newSessionThinkingMode.value,
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

// DeepAgents handlers
function handleUpdateEngine(engine: EngineType) {
  if (activeSession.value) {
    store.updateSession(activeSession.value.id, { engine })
  }
}

function handleUpdateCapabilities(capabilities: string[]) {
  if (activeSession.value) {
    store.updateSession(activeSession.value.id, { enabled_capabilities: capabilities as any })
  }
}

async function handleAddTodo(content: string, priority: number) {
  if (activeSession.value) {
    await store.addTodo(activeSession.value.id, content, priority)
  }
}

async function handleUpdateTodo(todoId: string, status: string) {
  if (activeSession.value) {
    await store.updateTodoStatus(activeSession.value.id, todoId, status as any)
  }
}

async function handleDeleteTodo(todoId: string) {
  if (activeSession.value) {
    await store.deleteTodo(activeSession.value.id, todoId)
  }
}

async function handleLoadSkill(skillName: string) {
  if (activeSession.value) {
    await store.loadSkill(activeSession.value.id, skillName)
  }
}

async function handleUnloadSkill(skillName: string) {
  if (activeSession.value) {
    await store.unloadSkill(activeSession.value.id, skillName)
  }
}

async function handleApproveFileOp(opId: string) {
  if (activeSession.value) {
    await store.approveFileOperation(activeSession.value.id, opId)
  }
}

async function handleRejectFileOp(opId: string, reason?: string) {
  if (activeSession.value) {
    await store.rejectFileOperation(activeSession.value.id, opId, reason)
  }
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
    <main class="main-content" :class="{ 'has-right-panel': activeRightPanel !== 'none' }">
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
        :engine="activeSession.engine || 'claude_sdk'"
        :enabled-capabilities="activeSession.enabled_capabilities || []"
        :input-tokens="activeSession.input_tokens || 0"
        :output-tokens="activeSession.output_tokens || 0"
        :todos="sessionTodos"
        :loaded-skills="activeSession.loaded_skills || []"
        :available-skills="skills"
        :pending-file-operation="sessionFileOps?.find(op => !op.approved) ?? null"
        @send="handleSendMessage"
        @interrupt="handleInterrupt"
        @update:engine="handleUpdateEngine"
        @update:capabilities="handleUpdateCapabilities"
        @add-todo="handleAddTodo"
        @update-todo="handleUpdateTodo"
        @delete-todo="handleDeleteTodo"
        @load-skill="handleLoadSkill"
        @unload-skill="handleUnloadSkill"
        @approve-file-op="handleApproveFileOp"
        @reject-file-op="handleRejectFileOp"
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

    <!-- Right Panel -->
    <aside v-if="activeRightPanel !== 'none'" class="right-panel">
      <BackgroundTaskPanel v-if="activeRightPanel === 'background'" />
      <CheckpointManager v-if="activeRightPanel === 'checkpoints'" />
      <MCPServerPanel v-if="activeRightPanel === 'mcp'" />
    </aside>

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

            <div class="form-row">
              <div class="form-group flex-1">
                <label>Engine</label>
                <select v-model="newSessionEngine">
                  <option v-for="e in engines" :key="e.value" :value="e.value">
                    {{ e.label }}
                  </option>
                </select>
              </div>
              <div class="form-group flex-1">
                <label>Model</label>
                <select v-model="newSessionModel">
                  <option v-for="m in availableModels" :key="m.value" :value="m.value">
                    {{ m.label }}
                  </option>
                </select>
              </div>
            </div>

            <div class="form-row">
              <div class="form-group flex-1">
                <label>Permission Mode</label>
                <select v-model="newSessionPermissionMode">
                  <option v-for="p in permissionModes" :key="p.value" :value="p.value">
                    {{ p.label }}
                  </option>
                </select>
              </div>
              <div class="form-group flex-1">
                <label>Thinking Mode</label>
                <select v-model="newSessionThinkingMode">
                  <option v-for="t in thinkingModes" :key="t.value" :value="t.value">
                    {{ t.label }}
                  </option>
                </select>
              </div>
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

    <!-- Keyboard Shortcuts Help -->
    <ShortcutsHelp />

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
  transition: margin-right 0.2s ease;
}

.main-content.has-right-panel {
  margin-right: 320px;
}

@media (max-width: 1024px) {
  .main-content.has-right-panel {
    margin-right: 0;
  }
}

@media (max-width: 768px) {
  .main-content {
    padding-top: 60px;
    padding-bottom: 60px;
  }
}

/* Top Bar */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
  flex-wrap: wrap;
  gap: 12px;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.top-bar-right {
  display: flex;
  align-items: center;
}

.plan-panel-inline {
  max-width: 300px;
}

/* Right Panel */
.right-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 320px;
  background: var(--color-bg);
  border-left: 1px solid var(--color-border);
  z-index: 70;
  overflow-y: auto;
}

@media (max-width: 1024px) {
  .right-panel {
    width: 100%;
    max-width: 400px;
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
  }
}

/* Bottom Toolbar */
.bottom-toolbar {
  position: fixed;
  bottom: 0;
  left: 280px;
  right: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: var(--color-bg-subtle);
  border-top: 1px solid var(--color-border);
  z-index: 60;
}

@media (max-width: 768px) {
  .bottom-toolbar {
    left: 0;
  }
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-center {
  display: flex;
  align-items: center;
  gap: 4px;
}

.toolbar-btn {
  position: relative;
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.toolbar-btn:hover {
  background: var(--color-bg-muted);
  color: var(--color-text);
}

.toolbar-btn.active {
  background: var(--color-accent);
  color: var(--color-bg);
  border-color: var(--color-accent);
}

.btn-icon {
  font-size: 14px;
}

.badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--color-accent);
  color: var(--color-bg);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.model-badge,
.thinking-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.model-badge {
  background: var(--color-bg-muted);
  color: var(--color-text-muted);
}

.thinking-badge {
  background: var(--color-warning-bg, #fef3c7);
  color: var(--color-warning, #f59e0b);
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
  max-width: 500px;
  padding: 1.5rem;
  border: 1px solid var(--color-border);
}

.new-session-modal h2 {
  margin: 0 0 1.5rem;
  font-size: 1.25rem;
}

.form-row {
  display: flex;
  gap: 12px;
}

.flex-1 {
  flex: 1;
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
  bottom: 5rem;
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
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  cursor: pointer;
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
  .permission-hint {
    display: none;
  }

  .top-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .top-bar-left,
  .top-bar-right {
    justify-content: center;
  }
}
</style>
