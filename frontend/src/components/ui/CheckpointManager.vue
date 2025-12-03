<script setup lang="ts">
import { ref, computed } from 'vue'
import { useInteractiveStore, type Checkpoint } from '@/stores/interactive'

const store = useInteractiveStore()

const newCheckpointName = ref('')
const isCreating = ref(false)

const checkpoints = computed(() => store.checkpoints)

async function createCheckpoint() {
  if (!newCheckpointName.value.trim()) return
  isCreating.value = true
  try {
    await store.createCheckpoint(newCheckpointName.value.trim())
    newCheckpointName.value = ''
  } finally {
    isCreating.value = false
  }
}

async function restoreCheckpoint(checkpoint: Checkpoint) {
  if (confirm(`Restore to checkpoint "${checkpoint.name}"? This will discard current changes.`)) {
    await store.restoreCheckpoint(checkpoint.id)
  }
}

async function deleteCheckpoint(checkpoint: Checkpoint) {
  if (confirm(`Delete checkpoint "${checkpoint.name}"?`)) {
    await store.deleteCheckpoint(checkpoint.id)
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString()
}
</script>

<template>
  <div class="checkpoint-manager">
    <div class="panel-header">
      <h3>Checkpoints</h3>
      <span class="checkpoint-count">{{ checkpoints.length }}</span>
    </div>

    <div class="create-checkpoint">
      <input
        v-model="newCheckpointName"
        type="text"
        placeholder="Checkpoint name..."
        @keyup.enter="createCheckpoint"
      />
      <button
        @click="createCheckpoint"
        :disabled="!newCheckpointName.trim() || isCreating"
      >
        {{ isCreating ? 'Creating...' : 'Create' }}
      </button>
    </div>

    <div class="checkpoint-list">
      <div
        v-for="checkpoint in checkpoints"
        :key="checkpoint.id"
        class="checkpoint-item"
      >
        <div class="checkpoint-info">
          <div class="checkpoint-name">{{ checkpoint.name }}</div>
          <div class="checkpoint-meta">
            <span class="checkpoint-time">{{ formatDate(checkpoint.created_at) }}</span>
            <span class="checkpoint-files">{{ checkpoint.file_count }} files</span>
            <span v-if="checkpoint.is_dirty" class="checkpoint-dirty">uncommitted</span>
          </div>
          <div v-if="checkpoint.description" class="checkpoint-description">
            {{ checkpoint.description }}
          </div>
        </div>
        <div class="checkpoint-actions">
          <button class="restore-btn" @click="restoreCheckpoint(checkpoint)" title="Restore">
            ↩
          </button>
          <button class="delete-btn" @click="deleteCheckpoint(checkpoint)" title="Delete">
            ✕
          </button>
        </div>
      </div>

      <div v-if="checkpoints.length === 0" class="empty-state">
        <div class="empty-icon">📸</div>
        <div class="empty-text">No checkpoints yet</div>
        <div class="empty-hint">Create a checkpoint to save your current state</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.checkpoint-manager {
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

.checkpoint-count {
  background: var(--color-bg-secondary, #f5f5f5);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
}

.create-checkpoint {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}

.create-checkpoint input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 6px;
  font-size: 13px;
}

.create-checkpoint button {
  padding: 8px 16px;
  background: var(--color-success, #22c55e);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}

.create-checkpoint button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.checkpoint-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.checkpoint-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px;
  border-radius: 6px;
  background: var(--color-bg-secondary, #f5f5f5);
  margin-bottom: 8px;
}

.checkpoint-info {
  flex: 1;
  min-width: 0;
}

.checkpoint-name {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
}

.checkpoint-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-secondary, #666);
}

.checkpoint-dirty {
  background: var(--color-warning-bg, #fef3c7);
  color: var(--color-warning, #d97706);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
}

.checkpoint-description {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
  font-style: italic;
}

.checkpoint-actions {
  display: flex;
  gap: 4px;
}

.restore-btn, .delete-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.restore-btn {
  background: var(--color-primary, #4f46e5);
  color: white;
}

.delete-btn {
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
