<script setup lang="ts">
import { ref } from 'vue'
import type { TodoItem, TodoStatus } from '@/stores/interactive'
import TodoItemComponent from './TodoItem.vue'

defineProps<{
  todos: TodoItem[]
}>()

const emit = defineEmits<{
  add: [content: string, priority: number]
  update: [todoId: string, status: TodoStatus]
  delete: [todoId: string]
}>()

const newTodoContent = ref('')
const showAddForm = ref(false)

function handleAdd() {
  if (!newTodoContent.value.trim()) return
  emit('add', newTodoContent.value.trim(), 0)
  newTodoContent.value = ''
  showAddForm.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleAdd()
  } else if (e.key === 'Escape') {
    showAddForm.value = false
    newTodoContent.value = ''
  }
}
</script>

<template>
  <div class="todo-panel">
    <div class="todo-header">
      <h3 class="todo-title">
        Tasks
        <span class="todo-count">{{ todos.length }}</span>
      </h3>
      <button
        class="add-btn"
        @click="showAddForm = !showAddForm"
        :title="showAddForm ? 'Cancel' : 'Add task'"
      >
        {{ showAddForm ? '×' : '+' }}
      </button>
    </div>

    <div v-if="showAddForm" class="add-form">
      <input
        v-model="newTodoContent"
        type="text"
        placeholder="Add a task..."
        class="add-input"
        @keydown="handleKeydown"
        autofocus
      />
      <button class="add-submit" @click="handleAdd" :disabled="!newTodoContent.trim()">
        Add
      </button>
    </div>

    <div class="todo-list" v-if="todos.length > 0">
      <TodoItemComponent
        v-for="todo in todos"
        :key="todo.id"
        :todo="todo"
        @update="(status) => emit('update', todo.id, status)"
        @delete="emit('delete', todo.id)"
      />
    </div>
    <div v-else class="todo-empty">
      No tasks yet. The agent will add tasks as it works.
    </div>
  </div>
</template>

<style scoped>
.todo-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-color, #1a1a1a);
  border-left: 1px solid var(--border-color, #333);
}

.todo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color, #333);
}

.todo-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-color, #e0e0e0);
}

.todo-count {
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  background: var(--accent-bg, rgba(90, 103, 216, 0.2));
  color: var(--accent-color, #5a67d8);
  font-size: 0.75rem;
}

.add-btn {
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: var(--bg-secondary, #252525);
  color: var(--text-color, #e0e0e0);
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.2s;
}

.add-btn:hover {
  background: var(--bg-hover, #333);
}

.add-form {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color, #333);
}

.add-input {
  flex: 1;
  padding: 0.5rem;
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  background: var(--bg-secondary, #252525);
  color: var(--text-color, #e0e0e0);
  font-size: 0.875rem;
}

.add-input:focus {
  outline: none;
  border-color: var(--accent-color, #5a67d8);
}

.add-submit {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  background: var(--accent-color, #5a67d8);
  color: white;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.add-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.todo-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.todo-empty {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--text-muted, #666);
  font-size: 0.875rem;
}
</style>
