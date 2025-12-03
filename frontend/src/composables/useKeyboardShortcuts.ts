import { onMounted, onUnmounted, ref } from 'vue'
import { useInteractiveStore } from '@/stores/interactive'

export interface ShortcutConfig {
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  meta?: boolean
  description: string
  action: () => void | Promise<void>
  when?: () => boolean
}

export function useKeyboardShortcuts(shortcuts: ShortcutConfig[] = []) {
  const store = useInteractiveStore()
  const isEnabled = ref(true)

  // Default shortcuts
  const defaultShortcuts: ShortcutConfig[] = [
    {
      key: 'Escape',
      description: 'Interrupt current operation',
      action: () => {
        if (store.isProcessing) {
          store.interrupt()
        }
      },
      when: () => store.isProcessing,
    },
    {
      key: 'p',
      ctrl: true,
      shift: true,
      description: 'Toggle Plan Mode',
      action: () => {
        store.setPlanMode(!store.planModeActive)
      },
      when: () => store.isActive,
    },
    {
      key: 's',
      ctrl: true,
      description: 'Create Checkpoint',
      action: async () => {
        const name = `checkpoint-${Date.now()}`
        await store.createCheckpoint(name)
      },
      when: () => store.isActive,
    },
    {
      key: 'm',
      ctrl: true,
      shift: true,
      description: 'Cycle Model',
      action: async () => {
        const models = store.models
        if (models.length === 0) return
        const currentIdx = models.findIndex(m => m.id === store.activeSession?.model)
        const nextIdx = (currentIdx + 1) % models.length
        const nextModel = models[nextIdx]
        if (nextModel) {
          await store.setModel(nextModel.id)
        }
      },
      when: () => store.isActive,
    },
    {
      key: 't',
      ctrl: true,
      shift: true,
      description: 'Cycle Thinking Mode',
      action: async () => {
        const modes = ['normal', 'think', 'think_hard', 'ultrathink'] as const
        const currentMode = store.thinkingMode ?? 'normal'
        const currentIdx = modes.indexOf(currentMode)
        const nextIdx = (currentIdx + 1) % modes.length
        const nextMode = modes[nextIdx]
        if (nextMode) {
          await store.setThinkingMode(nextMode)
        }
      },
      when: () => store.isActive,
    },
    {
      key: 'b',
      ctrl: true,
      shift: true,
      description: 'Toggle Background Tasks Panel',
      action: () => {
        store.showBackgroundPanel = !store.showBackgroundPanel
      },
    },
    {
      key: 'k',
      ctrl: true,
      shift: true,
      description: 'Toggle Checkpoints Panel',
      action: () => {
        store.showCheckpointsPanel = !store.showCheckpointsPanel
      },
    },
    {
      key: 'Enter',
      ctrl: true,
      description: 'Approve Permission',
      action: () => {
        if (store.isPendingPermission) {
          store.respondToPermission(true)
        }
      },
      when: () => store.isPendingPermission,
    },
    {
      key: 'Backspace',
      ctrl: true,
      description: 'Deny Permission',
      action: () => {
        if (store.isPendingPermission) {
          store.respondToPermission(false, 'Denied by user')
        }
      },
      when: () => store.isPendingPermission,
    },
  ]

  const allShortcuts = [...defaultShortcuts, ...shortcuts]

  function handleKeyDown(event: KeyboardEvent) {
    if (!isEnabled.value) return

    // Ignore if typing in input/textarea
    const target = event.target as HTMLElement
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      // Allow Escape and Ctrl+Enter in inputs
      if (event.key !== 'Escape' && !(event.ctrlKey && event.key === 'Enter')) {
        return
      }
    }

    for (const shortcut of allShortcuts) {
      const ctrlMatch = shortcut.ctrl ? (event.ctrlKey || event.metaKey) : !event.ctrlKey && !event.metaKey
      const shiftMatch = shortcut.shift ? event.shiftKey : !event.shiftKey
      const altMatch = shortcut.alt ? event.altKey : !event.altKey
      const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()

      if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
        // Check "when" condition
        if (shortcut.when && !shortcut.when()) {
          continue
        }

        event.preventDefault()
        event.stopPropagation()
        shortcut.action()
        return
      }
    }
  }

  function enable() {
    isEnabled.value = true
  }

  function disable() {
    isEnabled.value = false
  }

  function getShortcutList() {
    return allShortcuts.map(s => ({
      keys: formatShortcut(s),
      description: s.description,
    }))
  }

  function formatShortcut(config: ShortcutConfig): string {
    const parts: string[] = []
    if (config.ctrl) parts.push('Ctrl')
    if (config.shift) parts.push('Shift')
    if (config.alt) parts.push('Alt')
    if (config.meta) parts.push('Cmd')
    parts.push(config.key)
    return parts.join('+')
  }

  onMounted(() => {
    window.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown)
  })

  return {
    isEnabled,
    enable,
    disable,
    getShortcutList,
  }
}
