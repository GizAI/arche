import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

// Types matching backend models
export type SessionState =
  | 'idle'
  | 'thinking'
  | 'tool_executing'
  | 'permission_pending'
  | 'interrupted'
  | 'completed'
  | 'error'

export interface ContentBlock {
  type: 'text' | 'thinking' | 'tool_use' | 'tool_result'
  content: any
  tool_id?: string | null
  tool_name?: string | null
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool_use' | 'tool_result'
  content: ContentBlock[]
  timestamp: string
  metadata?: Record<string, any>
}

export interface PermissionRequest {
  request_id: string
  tool_name: string
  tool_input: Record<string, any>
  suggestions?: any[] | null
  created_at: string
}

export interface Session {
  id: string
  name: string
  state: SessionState
  created_at: string
  updated_at: string
  model: string
  cwd: string
  permission_mode: string
  current_turn: number
  total_cost_usd: number
  pending_permission: PermissionRequest | null
  message_count: number
  messages?: Message[]
}

export interface CreateSessionOptions {
  name?: string
  model?: string
  cwd?: string
  permission_mode?: string
  resume?: string // Session ID to resume from Claude CLI
}

export interface ExistingSession {
  session_id: string
  project_path: string
  cwd: string
  git_branch: string | null
  created_at: string
  updated_at: string
  message_count: number
  first_message_preview: string | null
  is_resumable: boolean
}

export interface ModelInfo {
  id: string
  name: string
  recommended?: boolean
}

export const useInteractiveStore = defineStore('interactive', () => {
  // State
  const sessions = ref<Session[]>([])
  const existingSessions = ref<ExistingSession[]>([])
  const models = ref<ModelInfo[]>([])
  const defaultModel = ref<string>('claude-sonnet-4-20250514')
  const activeSessionId = ref<string | null>(null)
  const activeSession = ref<Session | null>(null)
  const streamingText = ref('')
  const streamingThinking = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const wsConnected = ref(false)

  // WebSocket reference
  let ws: WebSocket | null = null
  let globalWs: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  // Computed
  const isActive = computed(() => activeSession.value !== null)
  const isProcessing = computed(() => {
    const state = activeSession.value?.state
    return state === 'thinking' || state === 'tool_executing'
  })
  const isPendingPermission = computed(() =>
    activeSession.value?.state === 'permission_pending'
  )
  const pendingPermission = computed(() =>
    activeSession.value?.pending_permission ?? null
  )
  const messages = computed(() => activeSession.value?.messages || [])

  // API Functions
  async function fetchSessions() {
    try {
      const res = await axios.get('/api/interactive/sessions')
      sessions.value = res.data.sessions
      // Also get existing sessions if returned
      if (res.data.existing_sessions) {
        existingSessions.value = res.data.existing_sessions
      }
      error.value = null
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to fetch sessions'
    }
  }

  async function fetchExistingSessions() {
    try {
      const res = await axios.get('/api/interactive/existing-sessions')
      existingSessions.value = res.data.sessions
      error.value = null
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to fetch existing sessions'
    }
  }

  async function fetchModels() {
    try {
      const res = await axios.get('/api/interactive/models')
      models.value = res.data.models
      defaultModel.value = res.data.default || 'claude-sonnet-4-20250514'
      error.value = null
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to fetch models'
    }
  }

  async function createSession(options: CreateSessionOptions = {}) {
    loading.value = true
    error.value = null
    try {
      const res = await axios.post('/api/interactive/sessions', options)
      sessions.value.push(res.data.session)
      return res.data.session as Session
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to create session'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteSession(sessionId: string) {
    loading.value = true
    error.value = null
    try {
      await axios.delete(`/api/interactive/sessions/${sessionId}`)
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      if (activeSessionId.value === sessionId) {
        activeSessionId.value = null
        activeSession.value = null
        disconnectSession()
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to delete session'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function selectSession(sessionId: string) {
    // Disconnect from previous session
    disconnectSession()

    activeSessionId.value = sessionId
    streamingText.value = ''
    streamingThinking.value = ''

    // Fetch session with messages
    try {
      const res = await axios.get(`/api/interactive/sessions/${sessionId}?include_messages=true`)
      activeSession.value = res.data.session
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to fetch session'
      return
    }

    // Connect WebSocket for real-time updates
    connectToSession(sessionId)
  }

  async function sendMessage(content: string, systemPrompt?: string) {
    if (!activeSessionId.value) return

    // Clear streaming buffers
    streamingText.value = ''
    streamingThinking.value = ''

    // Send via WebSocket if connected
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'send_message',
        content,
        system_prompt: systemPrompt,
      }))
    } else {
      // Fallback to REST API
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/messages`, {
          content,
          system_prompt: systemPrompt,
        })
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to send message'
        throw e
      }
    }
  }

  async function interrupt() {
    if (!activeSessionId.value) return

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/interrupt`)
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to interrupt'
      }
    }
  }

  async function respondToPermission(allow: boolean, reason?: string, modifiedInput?: Record<string, any>) {
    if (!activeSessionId.value || !pendingPermission.value) return

    const requestId = pendingPermission.value.request_id

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'permission_response',
        request_id: requestId,
        allow,
        reason,
        modified_input: modifiedInput,
      }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/permission`, {
          request_id: requestId,
          allow,
          reason,
          modified_input: modifiedInput,
        })
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to respond to permission'
      }
    }
  }

  async function updateSession(sessionId: string, updates: { name?: string; model?: string; permission_mode?: string }) {
    loading.value = true
    try {
      const res = await axios.patch(`/api/interactive/sessions/${sessionId}`, updates)

      // Update in sessions list
      const idx = sessions.value.findIndex(s => s.id === sessionId)
      if (idx >= 0) {
        sessions.value[idx] = { ...sessions.value[idx], ...res.data.session }
      }

      // Update active session if same
      if (activeSession.value?.id === sessionId) {
        activeSession.value = { ...activeSession.value, ...res.data.session }
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to update session'
      throw e
    } finally {
      loading.value = false
    }
  }

  // WebSocket Functions
  function connectToSession(sessionId: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/interactive/${sessionId}`)

    ws.onopen = () => {
      wsConnected.value = true
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data)
    }

    ws.onclose = () => {
      wsConnected.value = false
      // Attempt reconnect if still active
      if (activeSessionId.value === sessionId) {
        reconnectTimer = setTimeout(() => {
          if (activeSessionId.value === sessionId) {
            connectToSession(sessionId)
          }
        }, 2000)
      }
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function disconnectSession() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    wsConnected.value = false
  }

  function handleWebSocketMessage(data: any) {
    switch (data.type) {
      case 'session_state':
        activeSession.value = data.session
        break

      case 'state_change':
        if (activeSession.value) {
          activeSession.value.state = data.state
          // Update in sessions list
          const idx = sessions.value.findIndex(s => s.id === activeSession.value?.id)
          if (idx >= 0 && sessions.value[idx]) {
            sessions.value[idx]!.state = data.state
          }
        }
        break

      case 'message':
        if (activeSession.value) {
          if (!activeSession.value.messages) {
            activeSession.value.messages = []
          }
          activeSession.value.messages.push(data.message)
          activeSession.value.message_count = activeSession.value.messages.length

          // Clear streaming buffer when message is complete
          if (data.message.role === 'assistant') {
            streamingText.value = ''
            streamingThinking.value = ''
          }
        }
        break

      case 'stream':
        if (data.stream_type === 'text') {
          streamingText.value += data.content
        } else if (data.stream_type === 'thinking') {
          streamingThinking.value += data.content
        }
        break

      case 'tool_use':
        // Tool execution started - can show in UI
        break

      case 'tool_result':
        // Tool result received
        break

      case 'permission_request':
        if (activeSession.value) {
          activeSession.value.pending_permission = data.request
        }
        break

      case 'permission_response':
        if (activeSession.value) {
          activeSession.value.pending_permission = null
        }
        break

      case 'result':
        if (activeSession.value && data.cost_usd) {
          activeSession.value.total_cost_usd = data.cost_usd
        }
        break

      case 'error':
        error.value = data.error
        break

      case 'interrupted':
        // Session was interrupted
        break

      case 'ping':
        ws?.send(JSON.stringify({ type: 'pong' }))
        break
    }
  }

  // Global WebSocket for session list updates
  function connectGlobalWs() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    globalWs = new WebSocket(`${protocol}//${window.location.host}/ws/interactive`)

    globalWs.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'sessions_list') {
        sessions.value = data.sessions
      }
    }

    globalWs.onclose = () => {
      // Reconnect
      setTimeout(connectGlobalWs, 3000)
    }
  }

  function disconnectGlobalWs() {
    globalWs?.close()
    globalWs = null
  }

  // Cleanup
  function cleanup() {
    disconnectSession()
    disconnectGlobalWs()
  }

  return {
    // State
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
    wsConnected,

    // Computed
    isActive,
    isProcessing,
    isPendingPermission,
    pendingPermission,
    messages,

    // Actions
    fetchSessions,
    fetchExistingSessions,
    fetchModels,
    createSession,
    deleteSession,
    selectSession,
    sendMessage,
    interrupt,
    respondToPermission,
    updateSession,
    connectGlobalWs,
    disconnectGlobalWs,
    cleanup,
  }
})
