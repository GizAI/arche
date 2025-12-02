<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'

const store = useAgentStore()
const { status, loading, isRunning, isPaused } = storeToRefs(store)

// Start form
const showStartForm = ref(false)
const startForm = ref({
  goal: '',
  engine: 'claude_sdk',
  model: '',
  plan_mode: false,
  infinite: false,
  step: false,
})

// Feedback form
const showFeedbackForm = ref(false)
const feedbackForm = ref({
  message: '',
  priority: 'medium',
  interrupt: false,
})

async function handleStart() {
  if (!startForm.value.goal.trim()) return
  try {
    await store.start({
      goal: startForm.value.goal,
      engine: startForm.value.engine,
      model: startForm.value.model || null,
      plan_mode: startForm.value.plan_mode,
      infinite: startForm.value.infinite,
      step: startForm.value.step,
    })
    showStartForm.value = false
    startForm.value.goal = ''
  } catch (e) {
    // Error handled by store
  }
}

async function handleStop() {
  await store.stop()
}

async function handleResume(options?: { review?: boolean; retro?: boolean }) {
  await store.resume(options)
}

async function handlePause() {
  await store.pause()
}

async function handleFeedback() {
  if (!feedbackForm.value.message.trim()) return
  try {
    await store.submitFeedback(
      feedbackForm.value.message,
      feedbackForm.value.priority,
      feedbackForm.value.interrupt
    )
    showFeedbackForm.value = false
    feedbackForm.value.message = ''
    feedbackForm.value.interrupt = false
  } catch (e) {
    // Error handled by store
  }
}
</script>

<template>
  <div class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] p-4">
    <!-- Quick actions -->
    <div class="flex flex-wrap gap-3">
      <!-- Not running: Start or Resume -->
      <template v-if="!isRunning">
        <button
          @click="showStartForm = !showStartForm"
          :disabled="loading"
          class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-accent)] text-[var(--color-bg)] hover:bg-[var(--color-accent-muted)] disabled:opacity-50 transition-colors"
        >
          {{ showStartForm ? 'Cancel' : 'Start New' }}
        </button>
        <button
          v-if="status && status.turn > 1"
          @click="handleResume()"
          :disabled="loading"
          class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-bg-elevated)] text-[var(--color-text)] hover:bg-[var(--color-bg-muted)] disabled:opacity-50 transition-colors border border-[var(--color-border)]"
        >
          Resume
        </button>
        <button
          v-if="status && status.turn > 1"
          @click="handleResume({ review: true })"
          :disabled="loading"
          class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-bg-elevated)] text-[var(--color-text)] hover:bg-[var(--color-bg-muted)] disabled:opacity-50 transition-colors border border-[var(--color-border)]"
        >
          Resume (Review)
        </button>
      </template>

      <!-- Running: Pause or Stop -->
      <template v-else>
        <button
          v-if="!isPaused"
          @click="handlePause"
          :disabled="loading"
          class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-warning)] text-[var(--color-bg)] hover:opacity-80 disabled:opacity-50 transition-colors"
        >
          Pause
        </button>
        <button
          @click="handleStop"
          :disabled="loading"
          class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-error)] text-white hover:opacity-80 disabled:opacity-50 transition-colors"
        >
          Stop
        </button>
      </template>

      <!-- Feedback button -->
      <button
        @click="showFeedbackForm = !showFeedbackForm"
        class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-bg-elevated)] text-[var(--color-text)] hover:bg-[var(--color-bg-muted)] transition-colors border border-[var(--color-border)] ml-auto"
      >
        {{ showFeedbackForm ? 'Cancel' : '+ Feedback' }}
      </button>
    </div>

    <!-- Start form -->
    <div v-if="showStartForm" class="mt-4 pt-4 border-t border-[var(--color-border)]">
      <div class="grid gap-4 md:grid-cols-2">
        <div class="md:col-span-2">
          <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Goal</label>
          <textarea
            v-model="startForm.goal"
            rows="2"
            class="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none resize-none"
            placeholder="Describe what you want Arche to do..."
          />
        </div>
        <div>
          <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Engine</label>
          <select
            v-model="startForm.engine"
            class="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none"
          >
            <option value="claude_sdk">Claude SDK</option>
            <option value="codex">Codex</option>
            <option value="deepagents">DeepAgents</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Model (optional)</label>
          <input
            v-model="startForm.model"
            type="text"
            class="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none"
            placeholder="e.g., claude-3-opus"
          />
        </div>
        <div class="md:col-span-2 flex gap-6">
          <label class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input type="checkbox" v-model="startForm.plan_mode" class="accent-[var(--color-accent)]" />
            Plan mode
          </label>
          <label class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input type="checkbox" v-model="startForm.infinite" class="accent-[var(--color-accent)]" />
            Infinite
          </label>
          <label class="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input type="checkbox" v-model="startForm.step" class="accent-[var(--color-accent)]" />
            Step mode
          </label>
        </div>
        <div class="md:col-span-2">
          <button
            @click="handleStart"
            :disabled="loading || !startForm.goal.trim()"
            class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-accent)] text-[var(--color-bg)] hover:bg-[var(--color-accent-muted)] disabled:opacity-50 transition-colors"
          >
            Start Arche
          </button>
        </div>
      </div>
    </div>

    <!-- Feedback form -->
    <div v-if="showFeedbackForm" class="mt-4 pt-4 border-t border-[var(--color-border)]">
      <div class="grid gap-4">
        <div>
          <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Feedback Message</label>
          <textarea
            v-model="feedbackForm.message"
            rows="2"
            class="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none resize-none"
            placeholder="Your feedback for the agent..."
          />
        </div>
        <div class="flex gap-4 items-center">
          <div>
            <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Priority</label>
            <select
              v-model="feedbackForm.priority"
              class="px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>
          <label class="flex items-center gap-2 text-sm text-[var(--color-text-muted)] mt-4">
            <input type="checkbox" v-model="feedbackForm.interrupt" class="accent-[var(--color-accent)]" />
            Interrupt (review now)
          </label>
          <button
            @click="handleFeedback"
            :disabled="loading || !feedbackForm.message.trim()"
            class="px-4 py-2 rounded font-mono text-sm bg-[var(--color-accent)] text-[var(--color-bg)] hover:bg-[var(--color-accent-muted)] disabled:opacity-50 transition-colors mt-4 ml-auto"
          >
            Submit Feedback
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
