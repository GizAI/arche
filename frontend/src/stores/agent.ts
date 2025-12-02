import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

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
      const res = await axios.get('/api/status')
      status.value = res.data
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch status'
    }
  }

  async function start(options: StartOptions) {
    loading.value = true
    error.value = null
    try {
      await axios.post('/api/start', {
        goal: options.goal,
        engine: options.engine ?? 'claude_sdk',
        model: options.model ?? null,
        plan_mode: options.plan_mode ?? false,
        infinite: options.infinite ?? false,
        step: options.step ?? false,
        retro_every: options.retro_every ?? 'auto',
      })
      await fetchStatus()
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to start'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function stop() {
    loading.value = true
    error.value = null
    try {
      await axios.post('/api/stop')
      await fetchStatus()
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to stop'
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
      await axios.post(url)
      await fetchStatus()
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to resume'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function pause() {
    loading.value = true
    error.value = null
    try {
      await axios.post('/api/pause')
      await fetchStatus()
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to pause'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function submitFeedback(message: string, priority = 'medium', interrupt = false) {
    loading.value = true
    error.value = null
    try {
      await axios.post('/api/feedback', { message, priority, interrupt })
      return true
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to submit feedback'
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
