<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { PermissionRequest } from '@/stores/interactive'

const props = defineProps<{
  request: PermissionRequest | null
}>()

const emit = defineEmits<{
  respond: [allow: boolean, reason?: string, modifiedInput?: Record<string, any>]
}>()

const showModify = ref(false)
const modifiedInput = ref('')
const denyReason = ref('')

const isOpen = computed(() => props.request !== null)

const formattedInput = computed(() => {
  if (!props.request) return ''
  return JSON.stringify(props.request.tool_input, null, 2)
})

// Reset state when request changes
watch(() => props.request, () => {
  showModify.value = false
  modifiedInput.value = ''
  denyReason.value = ''
})

function handleAllow() {
  let modified: Record<string, any> | undefined
  if (showModify.value && modifiedInput.value) {
    try {
      modified = JSON.parse(modifiedInput.value)
    } catch {
      // Invalid JSON, ignore modification
    }
  }
  emit('respond', true, undefined, modified)
}

function handleDeny() {
  emit('respond', false, denyReason.value || 'User denied permission')
}

function toggleModify() {
  showModify.value = !showModify.value
  if (showModify.value && !modifiedInput.value) {
    modifiedInput.value = formattedInput.value
  }
}

function getToolIcon(toolName: string): string {
  const name = toolName.toLowerCase()
  if (name.includes('bash') || name.includes('shell')) return '&#128187;'
  if (name.includes('read')) return '&#128196;'
  if (name.includes('write') || name.includes('edit')) return '&#9998;'
  if (name.includes('glob') || name.includes('grep')) return '&#128269;'
  if (name.includes('web') || name.includes('fetch')) return '&#127760;'
  if (name.includes('task')) return '&#128203;'
  return '&#9881;'
}

function getDangerLevel(toolName: string): 'low' | 'medium' | 'high' {
  const name = toolName.toLowerCase()
  if (name.includes('bash') || name.includes('write') || name.includes('edit') || name.includes('delete')) {
    return 'high'
  }
  if (name.includes('web') || name.includes('fetch')) {
    return 'medium'
  }
  return 'low'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && request" class="modal-overlay" @click.self="handleDeny">
        <div class="modal-container" :class="getDangerLevel(request.tool_name)">
          <!-- Header -->
          <div class="modal-header">
            <div class="header-icon" v-html="getToolIcon(request.tool_name)"></div>
            <div class="header-text">
              <h2>Permission Request</h2>
              <p>Claude wants to use a tool</p>
            </div>
          </div>

          <!-- Tool Info -->
          <div class="tool-info">
            <div class="tool-name-row">
              <span class="label">Tool:</span>
              <code class="tool-name">{{ request.tool_name }}</code>
            </div>

            <div class="tool-input-section">
              <div class="section-header">
                <span class="label">Input:</span>
                <button class="modify-toggle" @click="toggleModify">
                  {{ showModify ? 'Cancel Edit' : 'Edit Input' }}
                </button>
              </div>

              <div v-if="!showModify" class="tool-input-display">
                <pre>{{ formattedInput }}</pre>
              </div>

              <textarea
                v-else
                v-model="modifiedInput"
                class="tool-input-edit"
                rows="8"
                spellcheck="false"
              ></textarea>
            </div>
          </div>

          <!-- Suggestions -->
          <div v-if="request.suggestions?.length" class="suggestions">
            <span class="label">Suggestions:</span>
            <div class="suggestion-list">
              <div
                v-for="(suggestion, idx) in request.suggestions"
                :key="idx"
                class="suggestion-item"
              >
                {{ suggestion.type }}: {{ suggestion.behavior }}
              </div>
            </div>
          </div>

          <!-- Deny Reason (optional) -->
          <div class="deny-reason-section">
            <label class="label">Deny reason (optional):</label>
            <input
              v-model="denyReason"
              type="text"
              placeholder="Why are you denying this request?"
              class="deny-reason-input"
            />
          </div>

          <!-- Actions -->
          <div class="modal-actions">
            <button class="btn btn-deny" @click="handleDeny">
              Deny
            </button>
            <button class="btn btn-allow" @click="handleAllow">
              {{ showModify ? 'Allow (Modified)' : 'Allow' }}
            </button>
          </div>

          <!-- Warning for dangerous tools -->
          <div v-if="getDangerLevel(request.tool_name) === 'high'" class="warning-banner">
            <span class="warning-icon">&#9888;</span>
            <span>This tool can modify files or execute commands. Review carefully.</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
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

.modal-container {
  background: var(--color-bg);
  border-radius: 16px;
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.modal-container.high {
  border-color: var(--color-error);
}

.modal-container.medium {
  border-color: var(--color-warning);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
}

.header-icon {
  font-size: 2rem;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-muted);
  border-radius: 12px;
}

.header-text h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.header-text p {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.tool-info {
  padding: 1.5rem;
}

.tool-name-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.label {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  font-weight: 500;
}

.tool-name {
  font-family: var(--font-mono);
  font-size: 0.9375rem;
  padding: 0.25rem 0.5rem;
  background: var(--color-accent);
  color: var(--color-bg);
  border-radius: 4px;
}

.tool-input-section {
  margin-top: 1rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.modify-toggle {
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.modify-toggle:hover {
  background: var(--color-bg-muted);
  color: var(--color-text);
}

.tool-input-display {
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem;
  max-height: 250px;
  overflow-y: auto;
}

.tool-input-display pre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text);
}

.tool-input-edit {
  width: 100%;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-accent);
  border-radius: 8px;
  padding: 1rem;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  color: var(--color-text);
  resize: vertical;
  outline: none;
}

.suggestions {
  padding: 0 1.5rem 1rem;
}

.suggestion-list {
  margin-top: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.suggestion-item {
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
  background: var(--color-bg-muted);
  border-radius: 4px;
  color: var(--color-text-muted);
}

.deny-reason-section {
  padding: 0 1.5rem 1rem;
}

.deny-reason-input {
  width: 100%;
  margin-top: 0.5rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg-subtle);
  color: var(--color-text);
  font-size: 0.875rem;
  outline: none;
  transition: border-color 0.15s ease;
}

.deny-reason-input:focus {
  border-color: var(--color-accent);
}

.modal-actions {
  display: flex;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid var(--color-border);
}

.btn {
  flex: 1;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: none;
}

.btn-deny {
  background: var(--color-bg-muted);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}

.btn-deny:hover {
  background: var(--color-error);
  color: white;
  border-color: var(--color-error);
}

.btn-allow {
  background: var(--color-success);
  color: white;
}

.btn-allow:hover {
  background: #16a34a;
}

.warning-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  background: rgba(234, 179, 8, 0.1);
  border-top: 1px solid var(--color-warning);
  color: var(--color-warning);
  font-size: 0.875rem;
}

.warning-icon {
  font-size: 1.125rem;
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

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95) translateY(10px);
}
</style>
