import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface AgentStatus {
  running: boolean
  pid: number | null
  turn: number
  goal: string | null
  mode: string
  engine: string
  last_mode: string | null
  infinite: boolean
  step: boolean
  paused: boolean
}

export interface StartOptions {
  goal: string
  engine?: string
  model?: string | null
  plan_mode?: boolean
  infinite?: boolean
  step?: boolean
  retro_every?: string
}

export const useAgentStore = defineStore('agent', () => {
  const status = ref<AgentStatus | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const logs = ref('')
  const wsConnected = ref(false)

  const isRunning = computed(() => status.value?.running ?? false)
  const isPaused = computed(() => status.value?.paused ?? false)

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      status.value = await res.json()
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch status'
    }
  }

  async function start(options: StartOptions) {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: options.goal,
          engine: options.engine ?? 'claude_sdk',
          model: options.model ?? null,
          plan_mode: options.plan_mode ?? false,
          infinite: options.infinite ?? false,
          step: options.step ?? false,
          retro_every: options.retro_every ?? 'auto',
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      await fetchStatus()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to start'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function stop() {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/stop', { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      await fetchStatus()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to stop'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function resume(options?: { review?: boolean; retro?: boolean }) {
    loading.value = true
    error.value = null
    try {
      const params = new URLSearchParams()
      if (options?.review) params.set('review', 'true')
      if (options?.retro) params.set('retro', 'true')
      const url = '/api/resume' + (params.toString() ? `?${params}` : '')
      const res = await fetch(url, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      await fetchStatus()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to resume'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function pause() {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/pause', { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      await fetchStatus()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to pause'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function submitFeedback(message: string, priority = 'medium', interrupt = false) {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, priority, interrupt }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to submit feedback'
      throw e
    } finally {
      loading.value = false
    }
  }

  function appendLog(content: string) {
    logs.value += content
    // Keep only last 50000 chars to avoid memory issues
    if (logs.value.length > 50000) {
      logs.value = logs.value.slice(-40000)
    }
  }

  function setLogs(content: string) {
    logs.value = content
  }

  function setWsConnected(connected: boolean) {
    wsConnected.value = connected
  }

  return {
    status,
    loading,
    error,
    logs,
    wsConnected,
    isRunning,
    isPaused,
    fetchStatus,
    start,
    stop,
    resume,
    pause,
    submitFeedback,
    appendLog,
    setLogs,
    setWsConnected,
  }
})
