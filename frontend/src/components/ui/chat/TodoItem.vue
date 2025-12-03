<script setup lang="ts">
import { computed } from 'vue'
import type { TodoItem, TodoStatus } from '@/stores/interactive'

const props = defineProps<{
  todo: TodoItem
}>()

const emit = defineEmits<{
  update: [status: TodoStatus]
  delete: []
}>()

const statusIcon = computed(() => {
  switch (props.todo.status) {
    case 'pending': return '○'
    case 'in_progress': return '◐'
    case 'completed': return '●'
    default: return '○'
  }
})

const statusClass = computed(() => `status-${props.todo.status.replace('_', '-')}`)

function cycleStatus() {
  const nextStatus: Record<TodoStatus, TodoStatus> = {
    pending: 'in_progress',
    in_progress: 'completed',
    completed: 'pending',
  }
  emit('update', nextStatus[props.todo.status])
}
</script>

<template>
  <div :class="['todo-item', statusClass]">
    <button class="status-btn" @click="cycleStatus" :title="`Status: ${todo.status}`">
      {{ statusIcon }}
    </button>
    <div class="todo-content">
      <span class="todo-text" :class="{ completed: todo.status === 'completed' }">
        {{ todo.content }}
      </span>
      <span v-if="todo.priority > 0" class="priority-badge">
        P{{ todo.priority }}
      </span>
    </div>
    <button class="delete-btn" @click="emit('delete')" title="Delete">
      ×
    </button>
  </div>
</template>

<style scoped>
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 6px;
  background: var(--bg-secondary, #252525);
  margin-bottom: 0.5rem;
  transition: background 0.2s;
}

.todo-item:hover {
  background: var(--bg-hover, #2a2a2a);
}

.todo-item.status-pending {
  border-left: 2px solid var(--text-muted, #666);
}

.todo-item.status-in-progress {
  border-left: 2px solid var(--warning-color, #f59e0b);
}

.todo-item.status-completed {
  border-left: 2px solid var(--success-color, #10b981);
  opacity: 0.7;
}

.status-btn {
  flex-shrink: 0;
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: none;
  font-size: 0.875rem;
  cursor: pointer;
  padding: 0;
}

.status-pending .status-btn {
  color: var(--text-muted, #666);
}

.status-in-progress .status-btn {
  color: var(--warning-color, #f59e0b);
}

.status-completed .status-btn {
  color: var(--success-color, #10b981);
}

.todo-content {
  flex: 1;
  min-width: 0;
}

.todo-text {
  display: block;
  font-size: 0.875rem;
  color: var(--text-color, #e0e0e0);
  word-break: break-word;
}

.todo-text.completed {
  text-decoration: line-through;
  color: var(--text-muted, #666);
}

.priority-badge {
  display: inline-block;
  margin-top: 0.25rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  background: var(--accent-bg, rgba(90, 103, 216, 0.2));
  color: var(--accent-color, #5a67d8);
  font-size: 0.625rem;
  font-weight: 600;
}

.delete-btn {
  flex-shrink: 0;
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: none;
  color: var(--text-muted, #666);
  font-size: 1rem;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s, color 0.2s;
}

.todo-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: var(--error-color, #ef4444);
}
</style>
