<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useInteractiveStore, type BackgroundTask } from '@/stores/interactive'

const store = useInteractiveStore()

const newCommand = ref('')
const selectedTaskId = ref<string | null>(null)
const taskOutput = ref<string[]>([])
const outputInterval = ref<ReturnType<typeof setInterval> | null>(null)

const tasks = computed(() => store.backgroundTasks)
const runningTasks = computed(() => store.runningTasks)

async function startTask() {
  if (!newCommand.value.trim()) return
  await store.runBackgroundTask(newCommand.value.trim())
  newCommand.value = ''
}

async function cancelTask(taskId: string) {
  await store.cancelBackgroundTask(taskId)
}

function selectTask(task: BackgroundTask) {
  selectedTaskId.value = task.id
  taskOutput.value = task.output_lines || []

  // Start polling for output if running
  if (task.status === 'running') {
    startOutputPolling(task.id)
  }
}

function startOutputPolling(taskId: string) {
  if (outputInterval.value) clearInterval(outputInterval.value)

  outputInterval.value = setInterval(async () => {
    const output = await store.getTaskOutput(taskId, taskOutput.value.length)
    if (output.length > 0) {
      taskOutput.value = [...taskOutput.value, ...output]
    }

    // Stop polling if task is no longer running
    const task = tasks.value.find(t => t.id === taskId)
    if (task && task.status !== 'running') {
      stopOutputPolling()
    }
  }, 1000)
}

function stopOutputPolling() {
  if (outputInterval.value) {
    clearInterval(outputInterval.value)
    outputInterval.value = null
  }
}

function getStatusColor(status: string) {
  switch (status) {
    case 'running': return 'var(--color-primary, #4f46e5)'
    case 'completed': return 'var(--color-success, #22c55e)'
    case 'failed': return 'var(--color-danger, #ef4444)'
    case 'cancelled': return 'var(--color-warning, #f59e0b)'
    default: return 'var(--color-text-secondary, #666)'
  }
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'running': return '⏳'
    case 'completed': return '✓'
    case 'failed': return '✗'
    case 'cancelled': return '⊘'
    default: return '○'
  }
}

watch(selectedTaskId, (newId) => {
  if (!newId) {
    stopOutputPolling()
  }
})

onUnmounted(() => {
  stopOutputPolling()
})
</script>

<template>
  <div class="background-task-panel">
    <div class="panel-header">
      <h3>Background Tasks</h3>
      <span v-if="runningTasks.length > 0" class="running-badge">
        {{ runningTasks.length }} running
      </span>
    </div>

    <div class="new-task">
      <input
        v-model="newCommand"
        type="text"
        placeholder="Enter command..."
        @keyup.enter="startTask"
      />
      <button @click="startTask" :disabled="!newCommand.trim()">Run</button>
    </div>

    <div class="task-list">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="task-item"
        :class="{ selected: selectedTaskId === task.id }"
        @click="selectTask(task)"
      >
        <span class="task-status" :style="{ color: getStatusColor(task.status) }">
          {{ getStatusIcon(task.status) }}
        </span>
        <span class="task-command">{{ task.command }}</span>
        <span class="task-time">{{ new Date(task.started_at).toLocaleTimeString() }}</span>
        <button
          v-if="task.status === 'running'"
          class="cancel-btn"
          @click.stop="cancelTask(task.id)"
        >
          Cancel
        </button>
      </div>
      <div v-if="tasks.length === 0" class="empty-state">
        No background tasks
      </div>
    </div>

    <div v-if="selectedTaskId" class="task-output">
      <div class="output-header">
        <span>Output</span>
        <button @click="selectedTaskId = null">Close</button>
      </div>
      <div class="output-content">
        <div v-for="(line, i) in taskOutput" :key="i" class="output-line">{{ line }}</div>
        <div v-if="taskOutput.length === 0" class="no-output">No output yet</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.background-task-panel {
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
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.running-badge {
  background: var(--color-primary, #4f46e5);
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}

.new-task {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}

.new-task input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 6px;
  font-size: 13px;
  font-family: monospace;
}

.new-task button {
  padding: 8px 16px;
  background: var(--color-primary, #4f46e5);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.new-task button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.task-item:hover {
  background: var(--color-bg-secondary, #f5f5f5);
}

.task-item.selected {
  background: var(--color-primary-bg, #eef2ff);
}

.task-status {
  font-size: 14px;
}

.task-command {
  flex: 1;
  font-family: monospace;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-time {
  font-size: 11px;
  color: var(--color-text-secondary, #666);
}

.cancel-btn {
  padding: 4px 8px;
  font-size: 11px;
  background: var(--color-danger, #ef4444);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: var(--color-text-secondary, #666);
  font-size: 13px;
}

.task-output {
  border-top: 1px solid var(--color-border, #e5e5e5);
  max-height: 200px;
  display: flex;
  flex-direction: column;
}

.output-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-bg-secondary, #f5f5f5);
  font-size: 12px;
  font-weight: 500;
}

.output-header button {
  padding: 2px 8px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 4px;
  cursor: pointer;
}

.output-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
  font-family: monospace;
  font-size: 11px;
  background: var(--color-bg-dark, #1e1e1e);
  color: var(--color-text-light, #fff);
}

.output-line {
  white-space: pre-wrap;
  word-break: break-all;
}

.no-output {
  color: var(--color-text-secondary, #888);
  font-style: italic;
}
</style>
