<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const isVisible = ref(false)

const shortcuts = [
  { keys: 'Escape', description: 'Interrupt current operation' },
  { keys: 'Ctrl+Shift+P', description: 'Toggle Plan Mode' },
  { keys: 'Ctrl+S', description: 'Create Checkpoint' },
  { keys: 'Ctrl+Shift+M', description: 'Cycle Model' },
  { keys: 'Ctrl+Shift+T', description: 'Cycle Thinking Mode' },
  { keys: 'Ctrl+Shift+B', description: 'Toggle Background Tasks Panel' },
  { keys: 'Ctrl+Shift+K', description: 'Toggle Checkpoints Panel' },
  { keys: 'Ctrl+Enter', description: 'Approve Permission' },
  { keys: 'Ctrl+Backspace', description: 'Deny Permission' },
  { keys: '?', description: 'Show this help' },
]

function handleKeyDown(event: KeyboardEvent) {
  if (event.key === '?' && !event.ctrlKey && !event.shiftKey && !event.altKey) {
    const target = event.target as HTMLElement
    if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA' && !target.isContentEditable) {
      event.preventDefault()
      isVisible.value = !isVisible.value
    }
  }
  if (event.key === 'Escape' && isVisible.value) {
    isVisible.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="isVisible" class="shortcuts-overlay" @click.self="isVisible = false">
        <div class="shortcuts-modal">
          <div class="modal-header">
            <h2>Keyboard Shortcuts</h2>
            <button class="close-btn" @click="isVisible = false">✕</button>
          </div>
          <div class="shortcuts-list">
            <div v-for="shortcut in shortcuts" :key="shortcut.keys" class="shortcut-item">
              <kbd class="shortcut-keys">{{ shortcut.keys }}</kbd>
              <span class="shortcut-desc">{{ shortcut.description }}</span>
            </div>
          </div>
          <div class="modal-footer">
            Press <kbd>?</kbd> to toggle this help
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.shortcuts-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.shortcuts-modal {
  background: var(--color-bg, #fff);
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  width: 90%;
  max-width: 400px;
  max-height: 80vh;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}

.modal-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: var(--color-text-secondary, #666);
}

.close-btn:hover {
  background: var(--color-bg-secondary, #f5f5f5);
}

.shortcuts-list {
  padding: 12px 20px;
  max-height: 400px;
  overflow-y: auto;
}

.shortcut-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-light, #f0f0f0);
}

.shortcut-item:last-child {
  border-bottom: none;
}

.shortcut-keys {
  display: inline-flex;
  gap: 4px;
  padding: 4px 8px;
  background: var(--color-bg-secondary, #f5f5f5);
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 6px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  font-weight: 500;
  min-width: 100px;
  justify-content: center;
}

.shortcut-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #666);
  text-align: right;
}

.modal-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--color-border, #e5e5e5);
  text-align: center;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
}

.modal-footer kbd {
  padding: 2px 6px;
  background: var(--color-bg-secondary, #f5f5f5);
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 11px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
