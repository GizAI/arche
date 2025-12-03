<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useInteractiveStore } from '@/stores/interactive'

const store = useInteractiveStore()

const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)

const sessionCost = computed(() => store.activeSession?.total_cost_usd || 0)
const usage = computed(() => store.usage)
const profile = computed(() => store.profile)

const utilizationPercent = computed(() => usage.value?.utilization_percent || 0)
const utilizationColor = computed(() => {
  if (utilizationPercent.value >= 90) return 'var(--color-danger, #ef4444)'
  if (utilizationPercent.value >= 70) return 'var(--color-warning, #f59e0b)'
  return 'var(--color-success, #22c55e)'
})

function formatCost(cost: number): string {
  return cost < 0.01 ? '<$0.01' : `$${cost.toFixed(2)}`
}

function formatTokens(tokens: number): string {
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(0)}K`
  return tokens.toString()
}

onMounted(() => {
  store.fetchUsage()
  // Refresh usage every minute
  refreshInterval.value = setInterval(() => {
    store.fetchUsage()
  }, 60000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<template>
  <div class="cost-tracker">
    <div class="session-cost">
      <span class="cost-label">Session</span>
      <span class="cost-value">{{ formatCost(sessionCost) }}</span>
    </div>

    <div class="divider"></div>

    <div v-if="usage" class="usage-info">
      <div class="usage-row">
        <span class="usage-label">Daily</span>
        <span class="usage-value">
          {{ formatCost(usage.daily_spend_usd) }}
          <span v-if="usage.daily_limit_usd" class="usage-limit">
            / {{ formatCost(usage.daily_limit_usd) }}
          </span>
        </span>
      </div>
      <div class="usage-row">
        <span class="usage-label">Monthly</span>
        <span class="usage-value">
          {{ formatCost(usage.monthly_spend_usd) }}
          <span v-if="usage.monthly_limit_usd" class="usage-limit">
            / {{ formatCost(usage.monthly_limit_usd) }}
          </span>
        </span>
      </div>
    </div>

    <div class="divider"></div>

    <div v-if="usage" class="rate-limit">
      <div class="rate-header">
        <span class="rate-label">5h Window</span>
        <span class="rate-tier" v-if="usage.rate_limit_tier">
          {{ usage.rate_limit_tier }}
        </span>
      </div>
      <div class="rate-bar">
        <div
          class="rate-fill"
          :style="{
            width: `${utilizationPercent}%`,
            background: utilizationColor
          }"
        ></div>
      </div>
      <div class="rate-info">
        <span>{{ formatTokens(usage.rolling_window_tokens) }} tokens</span>
        <span>{{ utilizationPercent.toFixed(0) }}%</span>
      </div>
    </div>

    <div v-if="profile" class="profile-info">
      <span class="profile-email">{{ profile.email }}</span>
    </div>
  </div>
</template>

<style scoped>
.cost-tracker {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--color-bg-secondary, #f5f5f5);
  border-radius: 8px;
  font-size: 12px;
}

.session-cost {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.cost-label {
  font-size: 10px;
  color: var(--color-text-secondary, #666);
  text-transform: uppercase;
}

.cost-value {
  font-weight: 600;
  font-size: 14px;
}

.divider {
  width: 1px;
  height: 32px;
  background: var(--color-border, #e5e5e5);
}

.usage-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.usage-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.usage-label {
  font-size: 10px;
  color: var(--color-text-secondary, #666);
  width: 48px;
}

.usage-value {
  font-weight: 500;
}

.usage-limit {
  color: var(--color-text-secondary, #666);
  font-weight: 400;
}

.rate-limit {
  min-width: 100px;
}

.rate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.rate-label {
  font-size: 10px;
  color: var(--color-text-secondary, #666);
}

.rate-tier {
  font-size: 9px;
  padding: 1px 4px;
  background: var(--color-primary, #4f46e5);
  color: white;
  border-radius: 4px;
  text-transform: uppercase;
}

.rate-bar {
  height: 4px;
  background: var(--color-bg, #fff);
  border-radius: 2px;
  overflow: hidden;
}

.rate-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.rate-info {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--color-text-secondary, #666);
  margin-top: 2px;
}

.profile-info {
  display: flex;
  align-items: center;
}

.profile-email {
  font-size: 10px;
  color: var(--color-text-secondary, #666);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .cost-tracker {
    flex-wrap: wrap;
    justify-content: center;
  }

  .divider {
    display: none;
  }
}
</style>
