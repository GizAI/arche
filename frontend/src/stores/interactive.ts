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

export type ThinkingMode = 'normal' | 'think' | 'think_hard' | 'ultrathink'

export type BackgroundTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type EngineType = 'claude_sdk' | 'deepagents'

export type TodoStatus = 'pending' | 'in_progress' | 'completed'

export type AgentCapability = 'filesystem' | 'planning' | 'subagent' | 'summarization'

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

export interface BackgroundTask {
  id: string
  command: string
  status: BackgroundTaskStatus
  started_at: string
  completed_at?: string | null
  exit_code?: number | null
  output_lines: string[]
}

export interface Checkpoint {
  id: string
  session_id: string
  name: string
  description: string | null
  created_at: string
  stash_ref: string
  file_count: number
  is_dirty: boolean
}

export interface MCPTool {
  name: string
  description: string
  input_schema: Record<string, any>
}

export interface MCPServer {
  name: string
  type: 'stdio' | 'sse' | 'http'
  status: 'disconnected' | 'connecting' | 'connected' | 'error'
  tool_count: number
  tools: MCPTool[]
  error_message?: string | null
  connected_at?: string | null
  config: MCPServerConfig
}

export interface MCPServerConfig {
  name: string
  type: 'stdio' | 'sse' | 'http'
  command?: string | null
  args?: string[]
  env?: Record<string, string>
  url?: string | null
  headers?: Record<string, string>
}

export interface HookConfig {
  id: string
  name: string
  type: 'pre_tool_use' | 'post_tool_use' | 'user_prompt_submit' | 'stop' | 'subagent_stop'
  enabled: boolean
  matcher?: string | null
  command?: string | null
  has_callback?: boolean
  timeout: number
}

export interface UsageInfo {
  daily_spend_usd: number
  monthly_spend_usd: number
  daily_limit_usd: number | null
  monthly_limit_usd: number | null
  rate_limit_tier: string | null
  rolling_window_seconds: number
  rolling_window_tokens: number
  rolling_window_limit: number | null
  utilization_percent: number
}

export interface ProfileInfo {
  user_id: string
  email: string
  name: string | null
  organization_id: string | null
  organization_name: string | null
}

export interface CustomCommand {
  name: string
  description: string
  type: 'builtin' | 'custom'
  arguments?: string[]
}

// DeepAgents specific interfaces
export interface TodoItem {
  id: string
  content: string
  status: TodoStatus
  priority: number
  created_at: string
  completed_at?: string | null
}

export interface SubAgentTask {
  id: string
  goal: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  parent_session_id: string
  result?: string | null
  created_at: string
  completed_at?: string | null
}

export interface FileOperation {
  id: string
  operation: string
  path: string
  content_preview?: string | null
  diff?: string | null
  approved: boolean
  result?: string | null
  timestamp: string
}

export interface SkillInfo {
  name: string
  description: string
  path?: string
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
  // Extended fields
  thinking_mode?: ThinkingMode
  plan_mode_active?: boolean
  proposed_plan?: Record<string, any> | null
  budget_usd?: number | null
  system_prompt?: string | null
  // DeepAgents fields
  engine: EngineType
  enabled_capabilities: AgentCapability[]
  input_tokens: number
  output_tokens: number
  todos: TodoItem[]
  subagent_tasks: SubAgentTask[]
  file_operations: FileOperation[]
  loaded_skills: string[]
}

export interface CreateSessionOptions {
  name?: string
  model?: string
  cwd?: string
  permission_mode?: string
  resume?: string // Session ID to resume from Claude CLI
  thinking_mode?: ThinkingMode
  engine?: EngineType
  capabilities?: AgentCapability[]
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

  // Extended state for new features
  const backgroundTasks = ref<BackgroundTask[]>([])
  const checkpoints = ref<Checkpoint[]>([])
  const mcpServers = ref<MCPServer[]>([])
  const hooks = ref<HookConfig[]>([])
  const commands = ref<CustomCommand[]>([])
  const usage = ref<UsageInfo | null>(null)
  const profile = ref<ProfileInfo | null>(null)
  const skills = ref<SkillInfo[]>([])

  // UI state
  const showBackgroundPanel = ref(false)
  const showCheckpointsPanel = ref(false)
  const showMcpPanel = ref(false)
  const showHooksPanel = ref(false)
  const showCommandsPanel = ref(false)

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

  // Extended computed
  const thinkingMode = computed(() => activeSession.value?.thinking_mode || 'normal')
  const planModeActive = computed(() => activeSession.value?.plan_mode_active || false)
  const proposedPlan = computed(() => activeSession.value?.proposed_plan || null)
  const runningTasks = computed(() => backgroundTasks.value.filter(t => t.status === 'running'))
  const connectedMcpServers = computed(() => mcpServers.value.filter(s => s.status === 'connected'))
  const mcpToolCount = computed(() => connectedMcpServers.value.reduce((sum, s) => sum + s.tool_count, 0))
  const sessionTodos = computed(() => activeSession.value?.todos || [])
  const sessionSubagents = computed(() => activeSession.value?.subagent_tasks || [])
  const sessionFileOps = computed(() => activeSession.value?.file_operations || [])

  // API Functions
  async function fetchSessions() {
    try {
      const res = await axios.get('/api/interactive/sessions')
      sessions.value = res.data.sessions
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
    disconnectSession()
    activeSessionId.value = sessionId
    streamingText.value = ''
    streamingThinking.value = ''

    try {
      const res = await axios.get(`/api/interactive/sessions/${sessionId}?include_messages=true`)
      activeSession.value = res.data.session
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to fetch session'
      return
    }

    connectToSession(sessionId)
    await Promise.all([
      fetchBackgroundTasks(sessionId),
      fetchCheckpoints(sessionId),
    ])
  }

  async function sendMessage(content: string, systemPrompt?: string) {
    if (!activeSessionId.value) return
    streamingText.value = ''
    streamingThinking.value = ''

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'send_message', content, system_prompt: systemPrompt }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/messages`, {
          content, system_prompt: systemPrompt,
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
        type: 'permission_response', request_id: requestId, allow, reason, modified_input: modifiedInput,
      }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/permission`, {
          request_id: requestId, allow, reason, modified_input: modifiedInput,
        })
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to respond to permission'
      }
    }
  }

  async function updateSession(sessionId: string, updates: { name?: string; model?: string; permission_mode?: string; engine?: EngineType; enabled_capabilities?: AgentCapability[] }) {
    loading.value = true
    try {
      const res = await axios.patch(`/api/interactive/sessions/${sessionId}`, updates)
      const idx = sessions.value.findIndex(s => s.id === sessionId)
      if (idx >= 0) sessions.value[idx] = { ...sessions.value[idx], ...res.data.session }
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

  // Thinking Mode
  async function setThinkingMode(mode: ThinkingMode) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_thinking_mode', mode }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/thinking-mode`, { mode })
        if (activeSession.value) activeSession.value.thinking_mode = mode
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to set thinking mode'
      }
    }
  }

  // Plan Mode
  async function setPlanMode(enabled: boolean) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_plan_mode', enabled }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/plan-mode`, { enabled })
        if (activeSession.value) activeSession.value.plan_mode_active = enabled
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to set plan mode'
      }
    }
  }

  async function approvePlan() {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'approve_plan' }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/approve-plan`)
        if (activeSession.value) {
          activeSession.value.plan_mode_active = false
          activeSession.value.proposed_plan = null
        }
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to approve plan'
      }
    }
  }

  // Model
  async function setModel(model: string) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_model', model }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/model`, { model })
        if (activeSession.value) activeSession.value.model = model
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to set model'
      }
    }
  }

  // Budget
  async function setBudget(budgetUsd: number | null) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_budget', budget_usd: budgetUsd }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/budget`, { budget_usd: budgetUsd })
        if (activeSession.value) activeSession.value.budget_usd = budgetUsd
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to set budget'
      }
    }
  }

  // Background Tasks
  async function fetchBackgroundTasks(sessionId?: string) {
    const sid = sessionId || activeSessionId.value
    if (!sid) return
    try {
      const res = await axios.get(`/api/interactive/sessions/${sid}/background-tasks`)
      backgroundTasks.value = res.data.tasks
    } catch (e: any) {
      console.error('Failed to fetch background tasks:', e)
    }
  }

  async function runBackgroundTask(command: string, timeout?: number) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'run_background', command, timeout }))
    } else {
      try {
        const res = await axios.post(`/api/interactive/sessions/${activeSessionId.value}/background-tasks`, { command, timeout })
        backgroundTasks.value.push(res.data.task)
        return res.data.task as BackgroundTask
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to start background task'
        throw e
      }
    }
  }

  async function cancelBackgroundTask(taskId: string) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'cancel_background', task_id: taskId }))
    } else {
      try {
        await axios.delete(`/api/interactive/sessions/${activeSessionId.value}/background-tasks/${taskId}`)
        const idx = backgroundTasks.value.findIndex(t => t.id === taskId)
        const task = backgroundTasks.value[idx]
        if (idx >= 0 && task) task.status = 'cancelled'
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to cancel task'
      }
    }
  }

  async function getTaskOutput(taskId: string, sinceLine = 0): Promise<string[]> {
    if (!activeSessionId.value) return []
    try {
      const res = await axios.get(`/api/interactive/sessions/${activeSessionId.value}/background-tasks/${taskId}/output`, { params: { since_line: sinceLine } })
      return res.data.output
    } catch (e: any) {
      console.error('Failed to get task output:', e)
      return []
    }
  }

  // Checkpoints
  async function fetchCheckpoints(sessionId?: string) {
    const sid = sessionId || activeSessionId.value
    if (!sid) return
    try {
      const res = await axios.get(`/api/interactive/sessions/${sid}/checkpoints`)
      checkpoints.value = res.data.checkpoints
    } catch (e: any) {
      console.error('Failed to fetch checkpoints:', e)
    }
  }

  async function createCheckpoint(name: string) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'create_checkpoint', name }))
    } else {
      try {
        const res = await axios.post(`/api/interactive/sessions/${activeSessionId.value}/checkpoints`, { name })
        checkpoints.value.push(res.data.checkpoint)
        return res.data.checkpoint as Checkpoint
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to create checkpoint'
        throw e
      }
    }
  }

  async function restoreCheckpoint(checkpointId: string) {
    if (!activeSessionId.value) return
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'restore_checkpoint', checkpoint_id: checkpointId }))
    } else {
      try {
        await axios.post(`/api/interactive/sessions/${activeSessionId.value}/checkpoints/${checkpointId}/restore`)
      } catch (e: any) {
        error.value = e.response?.data?.detail || e.message || 'Failed to restore checkpoint'
        throw e
      }
    }
  }

  async function deleteCheckpoint(checkpointId: string) {
    if (!activeSessionId.value) return
    try {
      await axios.delete(`/api/interactive/sessions/${activeSessionId.value}/checkpoints/${checkpointId}`)
      checkpoints.value = checkpoints.value.filter(c => c.id !== checkpointId)
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to delete checkpoint'
    }
  }

  // MCP Servers
  async function fetchMcpServers() {
    try {
      const res = await axios.get('/api/mcp/servers')
      mcpServers.value = res.data.servers
    } catch (e: any) {
      console.error('Failed to fetch MCP servers:', e)
    }
  }

  async function addMcpServer(config: MCPServerConfig) {
    try {
      const res = await axios.post('/api/mcp/servers', config)
      mcpServers.value.push(res.data.server)
      return res.data.server as MCPServer
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to add MCP server'
      throw e
    }
  }

  async function removeMcpServer(name: string) {
    try {
      await axios.delete(`/api/mcp/servers/${name}`)
      mcpServers.value = mcpServers.value.filter(s => s.name !== name)
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to remove MCP server'
    }
  }

  // Hooks
  async function fetchHooks() {
    try {
      const res = await axios.get('/api/hooks')
      hooks.value = res.data.hooks
    } catch (e: any) {
      console.error('Failed to fetch hooks:', e)
    }
  }

  async function addHook(config: Omit<HookConfig, 'id'>) {
    try {
      const res = await axios.post('/api/hooks', config)
      hooks.value.push(res.data.hook)
      return res.data.hook as HookConfig
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to add hook'
      throw e
    }
  }

  async function removeHook(hookId: string) {
    try {
      await axios.delete(`/api/hooks/${hookId}`)
      hooks.value = hooks.value.filter(h => h.id !== hookId)
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to remove hook'
    }
  }

  async function toggleHook(hookId: string, enabled: boolean) {
    try {
      await axios.patch(`/api/hooks/${hookId}`, { enabled })
      const idx = hooks.value.findIndex(h => h.id === hookId)
      const hook = hooks.value[idx]
      if (idx >= 0 && hook) hook.enabled = enabled
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to toggle hook'
    }
  }

  // Commands
  async function fetchCommands() {
    try {
      const res = await axios.get('/api/commands')
      commands.value = res.data.commands
    } catch (e: any) {
      console.error('Failed to fetch commands:', e)
    }
  }

  async function executeCommand(name: string, args: string[] = [], kwargs: Record<string, string> = {}) {
    try {
      const res = await axios.post(`/api/commands/${name}/execute`, { args, kwargs })
      return res.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to execute command'
      throw e
    }
  }

  // Usage/Profile
  async function fetchUsage(forceRefresh = false) {
    try {
      const res = await axios.get('/api/usage', { params: { force_refresh: forceRefresh } })
      usage.value = res.data.usage
    } catch (e: any) {
      console.error('Failed to fetch usage:', e)
    }
  }

  async function fetchProfile(forceRefresh = false) {
    try {
      const res = await axios.get('/api/profile', { params: { force_refresh: forceRefresh } })
      profile.value = res.data.profile
    } catch (e: any) {
      console.error('Failed to fetch profile:', e)
    }
  }

  // Todo Management
  async function addTodo(sessionId: string, content: string, priority = 0) {
    try {
      const res = await axios.post(`/api/interactive/sessions/${sessionId}/todos`, { content, priority })
      if (activeSession.value?.id === sessionId) {
        activeSession.value.todos = [...(activeSession.value.todos || []), res.data.todo]
      }
      return res.data.todo
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to add todo'
      throw e
    }
  }

  async function updateTodoStatus(sessionId: string, todoId: string, status: TodoStatus) {
    try {
      await axios.patch(`/api/interactive/sessions/${sessionId}/todos/${todoId}`, { status })
      if (activeSession.value?.id === sessionId) {
        const todo = activeSession.value.todos?.find(t => t.id === todoId)
        if (todo) todo.status = status
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to update todo'
    }
  }

  async function deleteTodo(sessionId: string, todoId: string) {
    try {
      await axios.delete(`/api/interactive/sessions/${sessionId}/todos/${todoId}`)
      if (activeSession.value?.id === sessionId) {
        activeSession.value.todos = (activeSession.value.todos || []).filter(t => t.id !== todoId)
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to delete todo'
    }
  }

  // File Operation Approval
  async function approveFileOperation(sessionId: string, opId: string) {
    try {
      await axios.post(`/api/interactive/sessions/${sessionId}/file-operations/${opId}/approve`)
      if (activeSession.value?.id === sessionId) {
        const op = activeSession.value.file_operations?.find(f => f.id === opId)
        if (op) op.approved = true
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to approve file operation'
    }
  }

  async function rejectFileOperation(sessionId: string, opId: string, reason?: string) {
    try {
      await axios.post(`/api/interactive/sessions/${sessionId}/file-operations/${opId}/reject`, { reason })
      if (activeSession.value?.id === sessionId) {
        activeSession.value.file_operations = (activeSession.value.file_operations || []).filter(f => f.id !== opId)
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to reject file operation'
    }
  }

  // Skills
  async function fetchSkills() {
    try {
      const res = await axios.get('/api/interactive/skills')
      skills.value = res.data.skills
    } catch (e: any) {
      console.error('Failed to fetch skills:', e)
    }
  }

  async function loadSkill(sessionId: string, skillName: string) {
    try {
      await axios.post(`/api/interactive/sessions/${sessionId}/skills/${skillName}`)
      if (activeSession.value?.id === sessionId) {
        activeSession.value.loaded_skills = [...(activeSession.value.loaded_skills || []), skillName]
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to load skill'
    }
  }

  async function unloadSkill(sessionId: string, skillName: string) {
    try {
      await axios.delete(`/api/interactive/sessions/${sessionId}/skills/${skillName}`)
      if (activeSession.value?.id === sessionId) {
        activeSession.value.loaded_skills = (activeSession.value.loaded_skills || []).filter(s => s !== skillName)
      }
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || 'Failed to unload skill'
    }
  }

  // WebSocket Functions
  function connectToSession(sessionId: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/interactive/${sessionId}`)

    ws.onopen = () => { wsConnected.value = true }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data)
    }

    ws.onclose = () => {
      wsConnected.value = false
      if (activeSessionId.value === sessionId) {
        reconnectTimer = setTimeout(() => {
          if (activeSessionId.value === sessionId) connectToSession(sessionId)
        }, 2000)
      }
    }

    ws.onerror = () => { ws?.close() }
  }

  function disconnectSession() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (ws) { ws.close(); ws = null }
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
          const idx = sessions.value.findIndex(s => s.id === activeSession.value?.id)
          if (idx >= 0 && sessions.value[idx]) sessions.value[idx]!.state = data.state
        }
        break

      case 'message':
        if (activeSession.value) {
          if (!activeSession.value.messages) activeSession.value.messages = []
          activeSession.value.messages.push(data.message)
          activeSession.value.message_count = activeSession.value.messages.length
          if (data.message.role === 'assistant') {
            streamingText.value = ''
            streamingThinking.value = ''
          }
        }
        break

      case 'stream':
        if (data.stream_type === 'text') streamingText.value += data.content
        else if (data.stream_type === 'thinking') streamingThinking.value += data.content
        break

      case 'tool_use':
      case 'tool_result':
        break

      case 'permission_request':
        if (activeSession.value) activeSession.value.pending_permission = data.request
        break

      case 'permission_response':
        if (activeSession.value) activeSession.value.pending_permission = null
        break

      case 'result':
        if (activeSession.value && data.cost_usd) activeSession.value.total_cost_usd = data.cost_usd
        break

      case 'error':
        error.value = data.error
        break

      case 'interrupted':
        break

      case 'thinking_mode_changed':
        if (activeSession.value) activeSession.value.thinking_mode = data.mode
        break

      case 'plan_mode_changed':
        if (activeSession.value) activeSession.value.plan_mode_active = data.enabled
        break

      case 'plan_proposed':
        if (activeSession.value) activeSession.value.proposed_plan = data.plan
        break

      case 'background_task_update':
        {
          const task = data.task as BackgroundTask
          const taskIdx = backgroundTasks.value.findIndex(t => t.id === task.id)
          if (taskIdx >= 0) backgroundTasks.value[taskIdx] = task
          else backgroundTasks.value.push(task)
        }
        break

      case 'checkpoint_created':
        checkpoints.value.push(data.checkpoint)
        break

      case 'checkpoint_restored':
        break

      case 'mcp_server_update':
        {
          const server = data.server as MCPServer
          const serverIdx = mcpServers.value.findIndex(s => s.name === server.name)
          if (serverIdx >= 0) mcpServers.value[serverIdx] = server
          else mcpServers.value.push(server)
        }
        break

      case 'hook_executed':
        break

      case 'todo_update':
        if (activeSession.value) activeSession.value.todos = data.todos
        break

      case 'subagent_update':
        if (activeSession.value) {
          const task = data.task as SubAgentTask
          const subIdx = activeSession.value.subagent_tasks.findIndex(t => t.id === task.id)
          if (subIdx >= 0) activeSession.value.subagent_tasks[subIdx] = task
          else activeSession.value.subagent_tasks.push(task)
        }
        break

      case 'file_operation':
        if (activeSession.value) activeSession.value.file_operations.push(data.operation)
        break

      case 'ping':
        ws?.send(JSON.stringify({ type: 'pong' }))
        break
    }
  }

  function connectGlobalWs() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    globalWs = new WebSocket(`${protocol}//${window.location.host}/ws/interactive`)
    globalWs.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'sessions_list') sessions.value = data.sessions
    }
    globalWs.onclose = () => { setTimeout(connectGlobalWs, 3000) }
  }

  function disconnectGlobalWs() { globalWs?.close(); globalWs = null }

  function cleanup() { disconnectSession(); disconnectGlobalWs() }

  async function initializeExtended() {
    await Promise.all([fetchMcpServers(), fetchHooks(), fetchCommands(), fetchSkills(), fetchUsage(), fetchProfile()])
  }

  return {
    // State
    sessions, existingSessions, models, defaultModel, activeSessionId, activeSession,
    streamingText, streamingThinking, loading, error, wsConnected,
    // Extended state
    backgroundTasks, checkpoints, mcpServers, hooks, commands, usage, profile, skills,
    // UI state
    showBackgroundPanel, showCheckpointsPanel, showMcpPanel, showHooksPanel, showCommandsPanel,
    // Computed
    isActive, isProcessing, isPendingPermission, pendingPermission, messages,
    // Extended computed
    thinkingMode, planModeActive, proposedPlan, runningTasks, connectedMcpServers, mcpToolCount,
    sessionTodos, sessionSubagents, sessionFileOps,
    // Actions
    fetchSessions, fetchExistingSessions, fetchModels, createSession, deleteSession, selectSession,
    sendMessage, interrupt, respondToPermission, updateSession,
    connectGlobalWs, disconnectGlobalWs, cleanup,
    // Extended actions
    setThinkingMode, setPlanMode, approvePlan, setModel, setBudget,
    fetchBackgroundTasks, runBackgroundTask, cancelBackgroundTask, getTaskOutput,
    fetchCheckpoints, createCheckpoint, restoreCheckpoint, deleteCheckpoint,
    fetchMcpServers, addMcpServer, removeMcpServer,
    fetchHooks, addHook, removeHook, toggleHook,
    fetchCommands, executeCommand,
    fetchUsage, fetchProfile,
    fetchSkills, loadSkill, unloadSkill,
    // Todo & FileOp actions
    addTodo, updateTodoStatus, deleteTodo,
    approveFileOperation, rejectFileOperation,
    initializeExtended,
  }
})
