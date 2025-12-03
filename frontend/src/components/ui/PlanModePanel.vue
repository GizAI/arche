<script setup lang="ts">
import { computed } from 'vue'
import { useInteractiveStore } from '@/stores/interactive'

const store = useInteractiveStore()

const isActive = computed(() => store.planModeActive)
const proposedPlan = computed(() => store.proposedPlan)

async function togglePlanMode() {
  await store.setPlanMode(!isActive.value)
}

async function approvePlan() {
  await store.approvePlan()
}
</script>

<template>
  <div class="plan-mode-panel" :class="{ active: isActive }">
    <div class="plan-header">
      <div class="plan-info">
        <span class="plan-icon">📋</span>
        <span class="plan-title">Plan Mode</span>
        <span v-if="isActive" class="plan-badge">Read-Only</span>
      </div>
      <button class="toggle-btn" :class="{ active: isActive }" @click="togglePlanMode">
        {{ isActive ? 'Exit' : 'Enter' }}
      </button>
    </div>

    <div v-if="isActive" class="plan-description">
      Read-only exploration mode. Only read tools are available.
    </div>

    <div v-if="proposedPlan" class="proposed-plan">
      <div class="plan-section-title">Proposed Plan</div>
      <pre class="plan-content">{{ JSON.stringify(proposedPlan, null, 2) }}</pre>
      <div class="plan-actions">
        <button class="approve-btn" @click="approvePlan">Approve Plan</button>
        <button class="reject-btn" @click="togglePlanMode">Reject</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-mode-panel {
  background: var(--color-bg-secondary, #f5f5f5);
  border-radius: 8px;
  padding: 12px;
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.plan-mode-panel.active {
  background: var(--color-warning-bg, #fef3c7);
  border-color: var(--color-warning, #f59e0b);
}

.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.plan-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-icon {
  font-size: 16px;
}

.plan-title {
  font-weight: 600;
  font-size: 14px;
}

.plan-badge {
  background: var(--color-warning, #f59e0b);
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.toggle-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  background: var(--color-primary, #4f46e5);
  color: white;
  transition: all 0.15s ease;
}

.toggle-btn.active {
  background: var(--color-danger, #ef4444);
}

.toggle-btn:hover {
  opacity: 0.9;
}

.plan-description {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
}

.proposed-plan {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border, #e5e5e5);
}

.plan-section-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}

.plan-content {
  background: var(--color-bg, #fff);
  padding: 12px;
  border-radius: 6px;
  font-size: 11px;
  overflow-x: auto;
  max-height: 200px;
  margin: 0;
}

.plan-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.approve-btn {
  flex: 1;
  padding: 8px;
  border: none;
  border-radius: 6px;
  background: var(--color-success, #22c55e);
  color: white;
  font-weight: 500;
  cursor: pointer;
}

.reject-btn {
  flex: 1;
  padding: 8px;
  border: none;
  border-radius: 6px;
  background: var(--color-danger, #ef4444);
  color: white;
  font-weight: 500;
  cursor: pointer;
}
</style>
