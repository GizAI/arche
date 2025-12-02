<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'

const filesStore = useFilesStore()
const agentStore = useAgentStore()
const { status } = storeToRefs(agentStore)

const projectRules = ref('')
const projectRulesOriginal = ref('')
const saving = ref(false)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)

const hasChanges = ref(false)

onMounted(async () => {
  agentStore.fetchStatus()
  try {
    const file = await filesStore.readFile('PROJECT_RULES.md')
    if (file) {
      projectRules.value = file.content
      projectRulesOriginal.value = file.content
    }
  } catch {
    projectRules.value = '# Project Rules\n\n*Add your project-specific rules here*\n'
    projectRulesOriginal.value = projectRules.value
  }
})

watch(projectRules, () => {
  hasChanges.value = projectRules.value !== projectRulesOriginal.value
  saveSuccess.value = false
})

async function saveRules() {
  saving.value = true
  saveError.value = null
  saveSuccess.value = false
  try {
    await filesStore.writeFile('PROJECT_RULES.md', projectRules.value)
    projectRulesOriginal.value = projectRules.value
    hasChanges.value = false
    saveSuccess.value = true
    setTimeout(() => saveSuccess.value = false, 3000)
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : 'Failed to save'
  } finally {
    saving.value = false
  }
}

function resetRules() {
  projectRules.value = projectRulesOriginal.value
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- Header -->
    <h1 class="text-xl font-mono text-[var(--color-text)]">Settings</h1>

    <!-- Connection Info -->
    <div class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] p-4">
      <h2 class="text-sm font-mono text-[var(--color-text-muted)] mb-3">Connection</h2>
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span class="text-[var(--color-text-subtle)]">Status:</span>
          <span class="ml-2 text-[var(--color-text)]">
            {{ status?.running ? 'Running' : 'Stopped' }}
          </span>
        </div>
        <div>
          <span class="text-[var(--color-text-subtle)]">Engine:</span>
          <span class="ml-2 text-[var(--color-text)] font-mono">
            {{ status?.engine || 'N/A' }}
          </span>
        </div>
        <div>
          <span class="text-[var(--color-text-subtle)]">Turn:</span>
          <span class="ml-2 text-[var(--color-text)] font-mono">
            {{ status?.turn || 'N/A' }}
          </span>
        </div>
        <div>
          <span class="text-[var(--color-text-subtle)]">Mode:</span>
          <span class="ml-2 text-[var(--color-text)] font-mono">
            {{ status?.mode || 'N/A' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Project Rules Editor -->
    <div class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] overflow-hidden">
      <div class="px-4 py-3 border-b border-[var(--color-border)] flex items-center justify-between">
        <h2 class="text-sm font-mono text-[var(--color-text-muted)]">Project Rules</h2>
        <div class="flex items-center gap-2">
          <span v-if="saveSuccess" class="text-xs text-[var(--color-success)]">Saved!</span>
          <span v-if="saveError" class="text-xs text-[var(--color-error)]">{{ saveError }}</span>
          <button
            v-if="hasChanges"
            @click="resetRules"
            class="px-3 py-1 text-xs font-mono rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] border border-[var(--color-border)] hover:text-[var(--color-text)] transition-colors"
          >
            Reset
          </button>
          <button
            @click="saveRules"
            :disabled="saving || !hasChanges"
            class="px-3 py-1 text-xs font-mono rounded transition-colors"
            :class="hasChanges
              ? 'bg-[var(--color-accent)] text-[var(--color-bg)] hover:bg-[var(--color-accent-muted)]'
              : 'bg-[var(--color-bg-elevated)] text-[var(--color-text-subtle)] border border-[var(--color-border)]'"
          >
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
      <textarea
        v-model="projectRules"
        class="w-full h-96 p-4 bg-[var(--color-bg)] text-sm font-mono text-[var(--color-text)] resize-none outline-none"
        placeholder="# Project Rules..."
      />
    </div>

    <!-- Info -->
    <div class="text-xs text-[var(--color-text-subtle)]">
      <p>Project rules are included in every agent prompt. Use them to define:</p>
      <ul class="list-disc list-inside mt-1 space-y-0.5 text-[var(--color-text-subtle)]">
        <li>Coding standards and patterns</li>
        <li>Architecture decisions</li>
        <li>Anti-patterns to avoid</li>
        <li>Project-specific conventions</li>
      </ul>
    </div>
  </div>
</template>
