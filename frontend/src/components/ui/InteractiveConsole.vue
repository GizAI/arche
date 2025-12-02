<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import type { Message, ContentBlock, SessionState } from '@/stores/interactive'

const props = defineProps<{
  messages: Message[]
  streamingText: string
  streamingThinking: string
  sessionState: SessionState
  sessionName: string
  model: string
  totalCost: number
}>()

const emit = defineEmits<{
  send: [content: string]
  interrupt: []
  clear: []
  compact: []
}>()

const input = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const showThinking = ref(false)
const showSlashMenu = ref(false)

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
  <div class="console">
    <!-- Header -->
    <div class="console-header">
      <div class="header-left">
        <h2>{{ sessionName }}</h2>
        <span class="model-badge">{{ model }}</span>
      </div>
      <div class="header-right">
        <span class="cost" v-if="totalCost > 0">${{ totalCost.toFixed(4) }}</span>
        <span class="status-badge" :class="sessionState">
          {{ sessionState }}
        </span>
      </div>
    </div>

    <!-- Messages -->
    <div class="messages" ref="messagesContainer">
      <template v-for="msg in messages" :key="msg.id">
        <!-- User Message -->
        <div v-if="msg.role === 'user'" class="message user-message">
          <div class="message-header">
            <span class="role">You</span>
            <span class="time">{{ new Date(msg.timestamp).toLocaleTimeString() }}</span>
          </div>
          <div class="message-content">
            <template v-for="(block, idx) in msg.content" :key="idx">
              <div v-if="block.type === 'text'" class="text-block">
                {{ block.content }}
              </div>
            </template>
          </div>
        </div>

        <!-- Assistant Message -->
        <div v-else-if="msg.role === 'assistant'" class="message assistant-message">
          <div class="message-header">
            <span class="role">Claude</span>
            <span class="time">{{ new Date(msg.timestamp).toLocaleTimeString() }}</span>
          </div>
          <div class="message-content">
            <template v-for="(block, idx) in msg.content" :key="idx">
              <!-- Text -->
              <div v-if="block.type === 'text'" class="text-block">
                <pre class="text-pre">{{ block.content }}</pre>
              </div>

              <!-- Thinking -->
              <details v-else-if="block.type === 'thinking'" class="thinking-block">
                <summary>Thinking</summary>
                <pre class="thinking-content">{{ block.content }}</pre>
              </details>

              <!-- Tool Use -->
              <div v-else-if="block.type === 'tool_use'" class="tool-block tool-use">
                <div class="tool-header">
                  <span class="tool-icon">&#9881;</span>
                  <span class="tool-name">{{ block.tool_name }}</span>
                </div>
                <pre class="tool-args">{{ formatToolArgs(block.content) }}</pre>
              </div>

              <!-- Tool Result -->
              <div v-else-if="block.type === 'tool_result'" class="tool-block tool-result">
                <div class="tool-header">
                  <span class="tool-icon">&#10003;</span>
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
        <div class="message-header">
          <span class="role">Claude</span>
          <span class="streaming-indicator">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </span>
        </div>
        <div class="message-content">
          <!-- Streaming Thinking -->
          <details v-if="streamingThinking" class="thinking-block" :open="showThinking">
            <summary @click.prevent="showThinking = !showThinking">Thinking...</summary>
            <pre class="thinking-content">{{ streamingThinking }}</pre>
          </details>

          <!-- Streaming Text -->
          <div v-if="streamingText" class="text-block">
            <pre class="text-pre">{{ streamingText }}</pre>
          </div>
        </div>
      </div>

      <!-- Processing Indicator -->
      <div v-if="isProcessing && !streamingText && !streamingThinking" class="processing-indicator">
        <div class="spinner"></div>
        <span>{{ sessionState === 'tool_executing' ? 'Executing tool...' : 'Thinking...' }}</span>
      </div>
    </div>

    <!-- Input Area -->
    <div class="input-area">
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

      <div class="input-wrapper" :class="{ thinking: isThinking }">
        <textarea
          ref="inputRef"
          v-model="input"
          @keydown="handleKeydown"
          placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
          :disabled="sessionState === 'permission_pending'"
          rows="1"
        ></textarea>
        <div class="input-actions">
          <button
            v-if="isProcessing"
            class="interrupt-btn"
            @click="emit('interrupt')"
            title="Stop (Esc)"
          >
            &#9632;
          </button>
          <button
            v-else
            class="send-btn"
            @click="handleSend"
            :disabled="!canSend"
            title="Send (Enter)"
          >
            &#10148;
          </button>
        </div>
      </div>
      <div class="input-hints">
        <span class="hint">Shift+Enter for new line</span>
        <span class="hint">/ for commands</span>
        <span class="hint">Esc to cancel</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.console {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg);
}

.console-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-left h2 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.model-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background: var(--color-bg-muted);
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.cost {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.status-badge {
  padding: 0.25rem 0.625rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
}

.status-badge.idle { background: var(--color-bg-muted); color: var(--color-text-subtle); }
.status-badge.thinking { background: var(--color-accent); color: var(--color-bg); }
.status-badge.tool_executing { background: var(--color-info); color: var(--color-bg); }
.status-badge.permission_pending { background: var(--color-warning); color: var(--color-bg); }
.status-badge.completed { background: var(--color-success); color: white; }
.status-badge.error { background: var(--color-error); color: white; }
.status-badge.interrupted { background: var(--color-text-subtle); color: var(--color-bg); }

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.message {
  max-width: 85%;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.user-message {
  align-self: flex-end;
}

.assistant-message {
  align-self: flex-start;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-size: 0.75rem;
}

.role {
  font-weight: 600;
  color: var(--color-text);
}

.time {
  color: var(--color-text-subtle);
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.user-message .message-content {
  background: var(--color-accent);
  color: var(--color-bg);
  padding: 0.75rem 1rem;
  border-radius: 12px 12px 4px 12px;
}

.assistant-message .message-content {
  background: var(--color-bg-subtle);
  padding: 1rem;
  border-radius: 4px 12px 12px 12px;
  border: 1px solid var(--color-border);
}

.text-block {
  line-height: 1.6;
}

.text-pre {
  margin: 0;
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

.thinking-block {
  background: var(--color-bg-muted);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
}

.thinking-block summary {
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-muted);
  user-select: none;
}

.thinking-content {
  margin: 0.5rem 0 0;
  font-size: 0.875rem;
  color: var(--color-text-subtle);
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.tool-block {
  background: var(--color-bg-muted);
  border-radius: 6px;
  padding: 0.75rem;
  font-size: 0.875rem;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.tool-icon {
  font-size: 1rem;
}

.tool-use .tool-icon { color: var(--color-accent); }
.tool-result .tool-icon { color: var(--color-success); }

.tool-name {
  color: var(--color-accent);
  font-family: var(--font-mono);
}

.tool-args, .tool-output {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  color: var(--color-text-muted);
}

.streaming .message-content {
  border-color: var(--color-accent);
}

.streaming-indicator {
  display: flex;
  gap: 3px;
}

.streaming-indicator .dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: bounce 1.4s ease-in-out infinite;
}

.streaming-indicator .dot:nth-child(1) { animation-delay: 0s; }
.streaming-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.streaming-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-4px); }
}

.processing-indicator {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.input-area {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
}

.input-wrapper {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 0.75rem;
  transition: border-color 0.15s ease;
}

.input-wrapper:focus-within {
  border-color: var(--color-accent);
}

/* Thinking state - animated border */
.input-wrapper.thinking {
  border-color: var(--color-accent);
  animation: thinking-pulse 1.5s ease-in-out infinite;
}

@keyframes thinking-pulse {
  0%, 100% {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 0 transparent;
  }
  50% {
    border-color: var(--color-accent);
    box-shadow: 0 0 8px 2px rgba(var(--color-accent-rgb, 139, 92, 246), 0.3);
  }
}

.input-wrapper textarea {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 0.9375rem;
  line-height: 1.5;
  resize: none;
  min-height: 24px;
  max-height: 200px;
  outline: none;
}

.input-wrapper textarea::placeholder {
  color: var(--color-text-subtle);
}

.input-actions {
  display: flex;
  gap: 0.5rem;
}

.send-btn, .interrupt-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: none;
  font-size: 1.125rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.send-btn {
  background: var(--color-accent);
  color: var(--color-bg);
}

.send-btn:hover:not(:disabled) {
  background: var(--color-accent-muted);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.interrupt-btn {
  background: var(--color-error);
  color: white;
}

.interrupt-btn:hover {
  background: #dc2626;
}

/* Input hints */
.input-hints {
  display: flex;
  gap: 1rem;
  padding-top: 0.5rem;
  justify-content: center;
}

.hint {
  font-size: 0.675rem;
  color: var(--color-text-subtle);
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
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.15);
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

/* Input area needs position relative for slash menu */
.input-area {
  position: relative;
}
</style>
