<script setup lang="ts">
import { ref, computed } from 'vue'
import { useInteractiveStore, type MCPServerConfig, type MCPServer } from '@/stores/interactive'

const store = useInteractiveStore()

const showAddForm = ref(false)
const newServer = ref<MCPServerConfig>({
  name: '',
  type: 'stdio',
  command: '',
  args: [],
  env: {},
})
const argsInput = ref('')

const servers = computed(() => store.mcpServers)
const connectedServers = computed(() => store.connectedMcpServers)
const totalTools = computed(() => store.mcpToolCount)

function getStatusColor(status: string) {
  switch (status) {
    case 'connected': return 'var(--color-success, #22c55e)'
    case 'connecting': return 'var(--color-warning, #f59e0b)'
    case 'error': return 'var(--color-danger, #ef4444)'
    default: return 'var(--color-text-secondary, #666)'
  }
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'connected': return '●'
    case 'connecting': return '◐'
    case 'error': return '✕'
    default: return '○'
  }
}

async function addServer() {
  if (!newServer.value.name.trim()) return

  const config: MCPServerConfig = {
    ...newServer.value,
    args: argsInput.value ? argsInput.value.split(' ').filter(a => a) : [],
  }

  await store.addMcpServer(config)
  showAddForm.value = false
  resetForm()
}

function resetForm() {
  newServer.value = {
    name: '',
    type: 'stdio',
    command: '',
    args: [],
    env: {},
  }
  argsInput.value = ''
}

async function removeServer(server: MCPServer) {
  if (confirm(`Remove MCP server "${server.name}"?`)) {
    await store.removeMcpServer(server.name)
  }
}
</script>

<template>
  <div class="mcp-server-panel">
    <div class="panel-header">
      <div class="header-info">
        <h3>MCP Servers</h3>
        <div class="status-summary">
          <span class="connected-count">{{ connectedServers.length }} connected</span>
          <span class="tools-count">{{ totalTools }} tools</span>
        </div>
      </div>
      <button class="add-btn" @click="showAddForm = !showAddForm">
        {{ showAddForm ? 'Cancel' : '+ Add' }}
      </button>
    </div>

    <div v-if="showAddForm" class="add-form">
      <div class="form-group">
        <label>Name</label>
        <input v-model="newServer.name" type="text" placeholder="my-server" />
      </div>
      <div class="form-group">
        <label>Type</label>
        <select v-model="newServer.type">
          <option value="stdio">STDIO</option>
          <option value="sse">SSE</option>
          <option value="http">HTTP</option>
        </select>
      </div>
      <div v-if="newServer.type === 'stdio'" class="form-group">
        <label>Command</label>
        <input v-model="newServer.command" type="text" placeholder="npx" />
      </div>
      <div v-if="newServer.type === 'stdio'" class="form-group">
        <label>Arguments</label>
        <input v-model="argsInput" type="text" placeholder="-y @modelcontextprotocol/server" />
      </div>
      <div v-if="newServer.type !== 'stdio'" class="form-group">
        <label>URL</label>
        <input v-model="newServer.url" type="text" placeholder="https://..." />
      </div>
      <button class="submit-btn" @click="addServer" :disabled="!newServer.name.trim()">
        Add Server
      </button>
    </div>

    <div class="server-list">
      <div
        v-for="server in servers"
        :key="server.name"
        class="server-item"
      >
        <div class="server-status" :style="{ color: getStatusColor(server.status) }">
          {{ getStatusIcon(server.status) }}
        </div>
        <div class="server-info">
          <div class="server-name">{{ server.name }}</div>
          <div class="server-meta">
            <span class="server-type">{{ server.type.toUpperCase() }}</span>
            <span v-if="server.status === 'connected'" class="server-tools">
              {{ server.tool_count }} tools
            </span>
            <span v-if="server.error_message" class="server-error">
              {{ server.error_message }}
            </span>
          </div>
          <div v-if="server.tools.length > 0" class="tools-preview">
            <span v-for="tool in server.tools.slice(0, 3)" :key="tool.name" class="tool-badge">
              {{ tool.name }}
            </span>
            <span v-if="server.tools.length > 3" class="more-tools">
              +{{ server.tools.length - 3 }}
            </span>
          </div>
        </div>
        <button class="remove-btn" @click="removeServer(server)" title="Remove">
          ✕
        </button>
      </div>

      <div v-if="servers.length === 0" class="empty-state">
        <div class="empty-icon">🔌</div>
        <div class="empty-text">No MCP servers</div>
        <div class="empty-hint">Add a server to extend available tools</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mcp-server-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg, #fff);
  border-radius: 8px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}

.header-info h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.status-summary {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-secondary, #666);
  margin-top: 4px;
}

.add-btn {
  padding: 6px 12px;
  background: var(--color-primary, #4f46e5);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.add-form {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
  background: var(--color-bg-secondary, #f5f5f5);
}

.form-group {
  margin-bottom: 10px;
}

.form-group label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--color-text-secondary, #666);
}

.form-group input, .form-group select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 6px;
  font-size: 13px;
}

.submit-btn {
  width: 100%;
  padding: 10px;
  background: var(--color-success, #22c55e);
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.server-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.server-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 6px;
  background: var(--color-bg-secondary, #f5f5f5);
  margin-bottom: 8px;
}

.server-status {
  font-size: 16px;
  padding-top: 2px;
}

.server-info {
  flex: 1;
  min-width: 0;
}

.server-name {
  font-weight: 600;
  font-size: 13px;
}

.server-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--color-text-secondary, #666);
  margin-top: 2px;
}

.server-type {
  background: var(--color-bg, #fff);
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.server-error {
  color: var(--color-danger, #ef4444);
}

.tools-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.tool-badge {
  background: var(--color-bg, #fff);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-family: monospace;
}

.more-tools {
  font-size: 10px;
  color: var(--color-text-secondary, #666);
  padding: 2px 4px;
}

.remove-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary, #666);
  cursor: pointer;
}

.remove-btn:hover {
  background: var(--color-danger, #ef4444);
  color: white;
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--color-text-secondary, #666);
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-text {
  font-weight: 500;
  margin-bottom: 4px;
}

.empty-hint {
  font-size: 12px;
  opacity: 0.7;
}
</style>
