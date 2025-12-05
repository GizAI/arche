<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import type {
  Message,
  ContentBlock,
  SessionState,
  EngineType,
  AgentCapability,
  TodoItem,
  TodoStatus,
  FileOperation,
  SkillInfo,
} from '@/stores/interactive'

// Import DeepAgents components
import EngineSelector from './chat/EngineSelector.vue'
import CapabilityToggles from './chat/CapabilityToggles.vue'
import TokenCounter from './chat/TokenCounter.vue'
import TodoPanel from './chat/TodoPanel.vue'
import SkillSelector from './chat/SkillSelector.vue'
import FileOperationModal from './chat/FileOperationModal.vue'

const props = defineProps<{
  messages: Message[]
  streamingText: string
  streamingThinking: string
  sessionState: SessionState
  sessionName: string
  model: string
  totalCost: number
  // DeepAgents props
  engine: EngineType
  enabledCapabilities: AgentCapability[]
  inputTokens: number
  outputTokens: number
  todos: TodoItem[]
  loadedSkills: string[]
  availableSkills: SkillInfo[]
  pendingFileOperation: FileOperation | null
}>()

const emit = defineEmits<{
  send: [content: string]
  interrupt: []
  clear: []
  compact: []
  // DeepAgents events
  'update:engine': [engine: EngineType]
  'update:capabilities': [capabilities: AgentCapability[]]
  addTodo: [content: string, priority: number]
  updateTodo: [todoId: string, status: TodoStatus]
  deleteTodo: [todoId: string]
  loadSkill: [skillName: string]
  unloadSkill: [skillName: string]
  approveFileOp: [opId: string]
  rejectFileOp: [opId: string, reason?: string]
}>()

const input = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const showThinking = ref(false)
const showSlashMenu = ref(false)
const showTodoPanel = ref(false)
const inputFocused = ref(false)

// DeepAgents computed
const isDeepAgents = computed(() => props.engine === 'deepagents')
const hasTodos = computed(() => props.todos.length > 0)
const activeTodoCount = computed(() => props.todos.filter(t => t.status !== 'completed').length)

// Slash commands
const slashCommands = [
  { cmd: '/clear', desc: 'Clear conversation history', action: 'clear' },
  { cmd: '/compact', desc: 'Compact conversation to save tokens', action: 'compact' },
  { cmd: '/help', desc: 'Show available commands', action: 'help' },
]

const filteredCommands = computed(() => {
  if (!input.value.startsWith('/')) return []
  const query = input.value.toLowerCase()
  return slashCommands.filter(c => c.cmd.toLowerCase().startsWith(query))
})

const isProcessing = computed(() =>
  ['thinking', 'tool_executing'].includes(props.sessionState)
)

const isThinking = computed(() => props.sessionState === 'thinking' || props.streamingThinking)

const canSend = computed(() =>
  input.value.trim() && !isProcessing.value && props.sessionState !== 'permission_pending'
)

// Short model name for display
const shortModelName = computed(() => {
  const m = props.model
  if (m.includes('opus-4-5')) return 'Opus 4.5'
  if (m.includes('sonnet-4-5')) return 'Sonnet 4.5'
  if (m.includes('haiku-4-5')) return 'Haiku 4.5'
  if (m.includes('opus-4')) return 'Opus 4'
  if (m.includes('sonnet-4')) return 'Sonnet 4'
  if (m.includes('sonnet-3-7')) return 'Sonnet 3.7'
  if (m.includes('haiku')) return 'Haiku'
  if (m.includes('opus')) return 'Opus'
  return m.replace('claude-', '').split('-20')[0]
})

// Auto-scroll to bottom when new content arrives
watch(
  () => [props.messages.length, props.streamingText],
  async () => {
    await nextTick()
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  }
)

onMounted(() => {
  inputRef.value?.focus()
})

function handleSend() {
  if (!canSend.value) return

  const trimmed = input.value.trim()

  // Handle slash commands
  if (trimmed.startsWith('/')) {
    const cmd = slashCommands.find(c => c.cmd === trimmed)
    if (cmd) {
      handleSlashCommand(cmd.action)
      input.value = ''
      showSlashMenu.value = false
      return
    }
  }

  emit('send', trimmed)
  input.value = ''
  showSlashMenu.value = false
  nextTick(() => inputRef.value?.focus())
}

function handleSlashCommand(action: string) {
  switch (action) {
    case 'clear':
      emit('clear')
      break
    case 'compact':
      emit('compact')
      break
    case 'help':
      // Show help inline - can be expanded later
      break
  }
}

function selectSlashCommand(cmd: string) {
  input.value = cmd
  showSlashMenu.value = false
  handleSend()
}

function handleKeydown(e: KeyboardEvent) {
  // Show slash menu when typing /
  if (input.value === '/' || (input.value.startsWith('/') && filteredCommands.value.length > 0)) {
    showSlashMenu.value = true
  } else {
    showSlashMenu.value = false
  }

  // Tab to select first command
  if (e.key === 'Tab' && showSlashMenu.value && filteredCommands.value.length > 0) {
    e.preventDefault()
    selectSlashCommand(filteredCommands.value[0]!.cmd)
    return
  }

  // Escape to close slash menu
  if (e.key === 'Escape' && showSlashMenu.value) {
    e.preventDefault()
    showSlashMenu.value = false
    return
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// Watch input for slash menu
watch(input, (val) => {
  if (val.startsWith('/') && val.length > 0) {
    showSlashMenu.value = filteredCommands.value.length > 0
  } else {
    showSlashMenu.value = false
  }
})

function formatContent(block: ContentBlock): string {
  if (typeof block.content === 'string') {
    return block.content
  }
  return JSON.stringify(block.content, null, 2)
}

function formatToolArgs(args: any): string {
  if (!args) return ''
  if (typeof args === 'string') return args
  // Truncate long values
  const formatted = JSON.stringify(args, (_, v) => {
    if (typeof v === 'string' && v.length > 200) {
      return v.slice(0, 200) + '...'
    }
    return v
  }, 2)
  return formatted
}
</script>

<template>
  <div class="console" :class="{ 'with-todo-panel': showTodoPanel && isDeepAgents }">
    <!-- Main Area with Messages and optional Todo Panel -->
    <div class="main-area">
      <!-- Messages -->
      <div class="messages" ref="messagesContainer">
        <!-- Welcome message when empty -->
        <div v-if="messages.length === 0 && !streamingText && !streamingThinking" class="welcome-message">
          <div class="welcome-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
          </div>
          <h3>How can I help you today?</h3>
          <p class="welcome-subtitle">Ask me anything or give me a task to work on.</p>
        </div>

        <!-- Messages when not empty -->
        <div v-else class="messages-inner">
          <template v-for="msg in messages" :key="msg.id">
            <!-- User Message -->
            <div v-if="msg.role === 'user'" class="message user-message">
              <div class="message-avatar user-avatar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </svg>
              </div>
              <div class="message-body">
                <template v-for="(block, idx) in msg.content" :key="idx">
                  <div v-if="block.type === 'text'" class="text-block">
                    {{ block.content }}
                  </div>
                </template>
              </div>
            </div>

            <!-- Assistant Message -->
            <div v-else-if="msg.role === 'assistant'" class="message assistant-message">
              <div class="message-avatar assistant-avatar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 6v6l4 2"/>
                </svg>
              </div>
              <div class="message-body">
                <template v-for="(block, idx) in msg.content" :key="idx">
                  <!-- Text -->
                  <div v-if="block.type === 'text'" class="text-block">
                    <pre class="text-pre">{{ block.content }}</pre>
                  </div>

                  <!-- Thinking -->
                  <details v-else-if="block.type === 'thinking'" class="thinking-block">
                    <summary>
                      <span class="thinking-icon">💭</span>
                      <span>Thinking</span>
                    </summary>
                    <pre class="thinking-content">{{ block.content }}</pre>
                  </details>

                  <!-- Tool Use -->
                  <div v-else-if="block.type === 'tool_use'" class="tool-block tool-use">
                    <div class="tool-header">
                      <span class="tool-icon">⚡</span>
                      <span class="tool-name">{{ block.tool_name }}</span>
                    </div>
                    <pre class="tool-args">{{ formatToolArgs(block.content) }}</pre>
                  </div>

                  <!-- Tool Result -->
                  <div v-else-if="block.type === 'tool_result'" class="tool-block tool-result">
                    <div class="tool-header">
                      <span class="tool-icon">✓</span>
                      <span class="tool-label">Result</span>
                    </div>
                    <pre class="tool-output">{{ formatContent(block) }}</pre>
                  </div>
                </template>
              </div>
            </div>
          </template>

          <!-- Streaming Content -->
          <div v-if="streamingText || streamingThinking" class="message assistant-message streaming">
            <div class="message-avatar assistant-avatar">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
            <div class="message-body">
              <!-- Streaming Thinking -->
              <details v-if="streamingThinking" class="thinking-block" :open="showThinking">
                <summary @click.prevent="showThinking = !showThinking">
                  <span class="thinking-icon">💭</span>
                  <span>Thinking...</span>
                </summary>
                <pre class="thinking-content">{{ streamingThinking }}</pre>
              </details>

              <!-- Streaming Text -->
              <div v-if="streamingText" class="text-block">
                <pre class="text-pre">{{ streamingText }}<span class="cursor"></span></pre>
              </div>
            </div>
          </div>

          <!-- Processing Indicator -->
          <div v-if="isProcessing && !streamingText && !streamingThinking" class="message assistant-message">
            <div class="message-avatar assistant-avatar">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
            <div class="message-body processing-body">
              <span class="processing-text">{{ sessionState === 'tool_executing' ? 'Running...' : 'Thinking...' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Todo Panel (DeepAgents) -->
      <Transition name="todo-panel">
        <TodoPanel
          v-if="showTodoPanel && isDeepAgents"
          :todos="todos"
          @add="(content, priority) => emit('addTodo', content, priority)"
          @update="(id, status) => emit('updateTodo', id, status)"
          @delete="(id) => emit('deleteTodo', id)"
        />
      </Transition>
    </div>

    <!-- File Operation Modal (DeepAgents) -->
    <FileOperationModal
      v-if="pendingFileOperation"
      :operation="pendingFileOperation"
      @approve="emit('approveFileOp', $event)"
      @reject="(opId, reason) => emit('rejectFileOp', opId, reason)"
    />

    <!-- Input Area - ChatGPT Style -->
    <div class="input-area">
      <div class="input-container">
        <!-- Slash Command Menu -->
        <Transition name="slash-menu">
          <div v-if="showSlashMenu && filteredCommands.length > 0" class="slash-menu">
            <div
              v-for="cmd in filteredCommands"
              :key="cmd.cmd"
              class="slash-item"
              @click="selectSlashCommand(cmd.cmd)"
            >
              <span class="slash-cmd">{{ cmd.cmd }}</span>
              <span class="slash-desc">{{ cmd.desc }}</span>
            </div>
          </div>
        </Transition>

        <div class="input-wrapper" :class="{ thinking: isThinking, focused: inputFocused }">
          <textarea
            ref="inputRef"
            v-model="input"
            @keydown="handleKeydown"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
            placeholder="Message Claude..."
            :disabled="sessionState === 'permission_pending'"
            rows="1"
          ></textarea>
          <button
            v-if="isProcessing"
            class="action-btn stop-btn"
            @click="emit('interrupt')"
            title="Stop generating"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
          </button>
          <button
            v-else
            class="action-btn send-btn"
            @click="handleSend"
            :disabled="!canSend"
            title="Send message"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
          </button>
        </div>

        <div class="input-footer">
          <span class="model-info">{{ shortModelName }}</span>
          <span class="hint-text">Enter to send, Shift+Enter for new line</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ===== ChatGPT-Style Console ===== */
.console {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg);
}

/* Main area */
.main-area {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* Messages container */
.messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.messages-inner {
  max-width: 768px;
  width: 100%;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Welcome message */
.welcome-message {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 2rem;
  color: var(--color-text-muted);
}

.welcome-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-bg-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.5rem;
  color: var(--color-accent);
}

.welcome-message h3 {
  margin: 0 0 0.5rem;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text);
}

.welcome-subtitle {
  margin: 0;
  font-size: 0.9375rem;
  color: var(--color-text-muted);
}

/* Message styles */
.message {
  display: flex;
  gap: 1rem;
  animation: fadeIn 0.25s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-avatar {
  background: var(--color-accent);
  color: white;
}

.assistant-avatar {
  background: var(--color-bg-muted);
  color: var(--color-accent);
  border: 1px solid var(--color-border);
}

.message-body {
  flex: 1;
  min-width: 0;
  padding-top: 4px;
}

/* Text content */
.text-block {
  line-height: 1.7;
  color: var(--color-text);
}

.text-pre {
  margin: 0;
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Cursor animation for streaming */
.cursor {
  display: inline-block;
  width: 2px;
  height: 1.1em;
  background: var(--color-accent);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(1) { animation-delay: 0s; }
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

/* Processing state */
.processing-body {
  padding: 0.5rem 0;
}

.processing-text {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

/* Thinking block */
.thinking-block {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-top: 0.75rem;
  overflow: hidden;
}

.thinking-block summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.875rem;
  cursor: pointer;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  user-select: none;
  transition: background 0.15s;
}

.thinking-block summary:hover {
  background: var(--color-bg-muted);
}

.thinking-icon {
  font-size: 0.875rem;
}

.thinking-content {
  margin: 0;
  padding: 0.75rem;
  font-size: 0.8125rem;
  font-family: var(--font-mono);
  color: var(--color-text-subtle);
  white-space: pre-wrap;
  max-height: 300px;
  overflow-y: auto;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
}

/* Tool blocks */
.tool-block {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-top: 0.75rem;
  overflow: hidden;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  background: var(--color-bg-muted);
  border-bottom: 1px solid var(--color-border);
}

.tool-icon {
  font-size: 0.875rem;
}

.tool-use .tool-header { color: var(--color-accent); }
.tool-result .tool-header { color: var(--color-success); }

.tool-name {
  font-family: var(--font-mono);
}

.tool-args, .tool-output {
  margin: 0;
  padding: 0.75rem;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  color: var(--color-text-muted);
  background: var(--color-bg);
}

/* ===== Input Area - ChatGPT Style ===== */
.input-area {
  padding: 1rem;
  background: linear-gradient(to top, var(--color-bg) 50%, transparent);
}

.input-container {
  max-width: 768px;
  margin: 0 auto;
  position: relative;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 24px;
  padding: 0.75rem 1rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.2s ease;
}

.input-wrapper.focused,
.input-wrapper:focus-within {
  border-color: var(--color-accent);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
}

.input-wrapper.thinking {
  border-color: var(--color-accent);
  animation: pulse-border 2s ease-in-out infinite;
}

@keyframes pulse-border {
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  50% { box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.2); }
}

.input-wrapper textarea {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 1rem;
  line-height: 1.5;
  resize: none;
  min-height: 24px;
  max-height: 200px;
  outline: none;
  font-family: inherit;
}

.input-wrapper textarea::placeholder {
  color: var(--color-text-subtle);
}

/* Action buttons */
.action-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.send-btn {
  background: var(--color-accent);
  color: white;
}

.send-btn:hover:not(:disabled) {
  background: var(--color-accent-muted);
  transform: scale(1.05);
}

.send-btn:disabled {
  background: var(--color-bg-muted);
  color: var(--color-text-subtle);
  cursor: not-allowed;
}

.stop-btn {
  background: var(--color-error);
  color: white;
}

.stop-btn:hover {
  background: #dc2626;
  transform: scale(1.05);
}

/* Input footer */
.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.5rem 0;
  font-size: 0.6875rem;
  color: var(--color-text-subtle);
}

.model-info {
  font-family: var(--font-mono);
  background: var(--color-bg-muted);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

/* Slash Command Menu */
.slash-menu {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 0.5rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.slash-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: background 0.15s ease;
}

.slash-item:hover {
  background: var(--color-bg-muted);
}

.slash-cmd {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-accent);
}

.slash-desc {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.slash-menu-enter-active,
.slash-menu-leave-active {
  transition: all 0.15s ease;
}

.slash-menu-enter-from,
.slash-menu-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* Todo panel */
.console.with-todo-panel .main-area {
  gap: 0;
}

.todo-panel-enter-active,
.todo-panel-leave-active {
  transition: all 0.25s ease;
}

.todo-panel-enter-from,
.todo-panel-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

/* Responsive */
@media (max-width: 768px) {
  .messages-inner {
    padding: 1rem 0.75rem;
  }

  .input-container {
    padding: 0 0.5rem;
  }

  .input-wrapper {
    border-radius: 20px;
    padding: 0.625rem 0.875rem;
  }

  .welcome-message h3 {
    font-size: 1.25rem;
  }
}
</style>
