<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useAgentStore } from '@/stores/agent'
import { storeToRefs } from 'pinia'
import yaml from 'yaml'

const filesStore = useFilesStore()
const agentStore = useAgentStore()
const { tree, loading } = storeToRefs(filesStore)

const selectedFile = ref<string | null>(null)
const fileContent = ref<string>('')
const parsedYaml = ref<any>(null)

// New feedback form
const showNewForm = ref(false)
const submitting = ref(false)
const submitSuccess = ref(false)
const newFeedback = ref({
  message: '',
  priority: 'medium',
  interrupt: false,
})

const pendingFeedback = computed(() => filesStore.getFilesByDir('feedback'))
const archivedFeedback = computed(() => {
  if (!tree.value) return []
  const feedbackDir = tree.value.items.find(i => i.name === 'feedback' && i.type === 'directory')
  const archiveDir = feedbackDir?.children?.find(c => c.name === 'archive' && c.type === 'directory')
  return archiveDir?.children?.filter(c => c.type === 'file') ?? []
})

const activeTab = ref<'pending' | 'archived'>('pending')

onMounted(() => {
  filesStore.fetchTree()
})

async function selectFile(path: string) {
  selectedFile.value = path
  try {
    const file = await filesStore.readFile(path)
    if (file) {
      fileContent.value = file.content
      try {
        parsedYaml.value = yaml.parse(file.content)
      } catch {
        parsedYaml.value = null
      }
    }
  } catch {
    fileContent.value = 'Failed to load file'
  }
}

function formatDate(filename: string): string {
  const match = filename.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/)
  if (!match) return filename
  const [, year, month, day, hour, minute] = match
  return `${year}-${month}-${day} ${hour}:${minute}`
}

function getSummary(filename: string): string {
  const match = filename.match(/^\d{8}-\d{4}-(.+)\.yaml$/)
  return match ? match[1]!.replace(/-/g, ' ') : filename
}

function getPriorityStyle(priority: string): { bg: string; text: string } {
  const colors: Record<string, { bg: string; text: string }> = {
    low: { bg: 'rgba(163, 163, 163, 0.1)', text: 'var(--color-text-muted)' },
    medium: { bg: 'rgba(234, 179, 8, 0.1)', text: 'var(--color-warning)' },
    high: { bg: 'rgba(239, 68, 68, 0.1)', text: 'var(--color-error)' },
  }
  return colors[priority] ?? { bg: 'rgba(234, 179, 8, 0.1)', text: 'var(--color-warning)' }
}

const priorityColors: Record<string, { bg: string; text: string }> = {
  low: { bg: 'rgba(163, 163, 163, 0.1)', text: 'var(--color-text-muted)' },
  medium: { bg: 'rgba(234, 179, 8, 0.1)', text: 'var(--color-warning)' },
  high: { bg: 'rgba(239, 68, 68, 0.1)', text: 'var(--color-error)' },
}

async function submitFeedback() {
  if (!newFeedback.value.message.trim()) return
  submitting.value = true
  try {
    await agentStore.submitFeedback(
      newFeedback.value.message,
      newFeedback.value.priority,
      newFeedback.value.interrupt
    )
    submitSuccess.value = true
    await new Promise(resolve => setTimeout(resolve, 800))
    showNewForm.value = false
    newFeedback.value.message = ''
    newFeedback.value.interrupt = false
    await filesStore.fetchTree()
    submitSuccess.value = false
  } catch {
    // Error handled by store
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-mono text-[var(--color-text)]">Feedback</h1>
      <div class="flex items-center gap-2">
        <button
          @click="showNewForm = !showNewForm"
          class="px-3 py-1.5 text-xs font-mono rounded transition-colors"
          :class="showNewForm
            ? 'bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] border border-[var(--color-border)]'
            : 'bg-[var(--color-accent)] text-[var(--color-bg)]'"
        >
          {{ showNewForm ? 'Cancel' : '+ New Feedback' }}
        </button>
        <button
          @click="filesStore.fetchTree()"
          class="px-3 py-1.5 text-xs font-mono rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] border border-[var(--color-border)] hover:text-[var(--color-text)] transition-colors"
        >
          Refresh
        </button>
      </div>
    </div>

    <!-- New feedback form -->
    <div v-if="showNewForm" class="mb-4 bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] p-4">
      <div class="grid gap-4">
        <div>
          <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Message</label>
          <textarea
            v-model="newFeedback.message"
            rows="3"
            class="w-full px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none resize-none"
            placeholder="Your feedback..."
          />
        </div>
        <div class="flex items-center gap-4">
          <div>
            <label class="block text-xs text-[var(--color-text-subtle)] mb-1 font-mono">Priority</label>
            <select
              v-model="newFeedback.priority"
              class="px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-sm font-mono text-[var(--color-text)] focus:border-[var(--color-accent)] outline-none"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>
          <label class="flex items-center gap-2 text-sm text-[var(--color-text-muted)] mt-4">
            <input type="checkbox" v-model="newFeedback.interrupt" class="accent-[var(--color-accent)]" />
            Review immediately
          </label>
          <button
            @click="submitFeedback"
            :disabled="!newFeedback.message.trim() || submitting"
            class="px-4 py-2 rounded font-mono text-sm transition-all duration-300 mt-4 ml-auto relative overflow-hidden"
            :class="submitSuccess
              ? 'bg-[var(--color-success)] text-white'
              : 'bg-[var(--color-accent)] text-[var(--color-bg)] hover:bg-[var(--color-accent-muted)] disabled:opacity-50'"
          >
            <span v-if="!submitSuccess">{{ submitting ? 'Submitting...' : 'Submit' }}</span>
            <span v-else class="inline-block success-check">✓</span>
          </button>
        </div>
      </div>
    </div>

    <div class="flex-1 flex flex-col md:flex-row gap-4 min-h-0">
      <!-- File list -->
      <div
        class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] overflow-hidden flex flex-col"
        :class="selectedFile ? 'hidden md:flex md:w-80' : 'flex-1 md:flex-none md:w-80'"
      >
        <!-- Tabs -->
        <div class="flex border-b border-[var(--color-border)]">
          <button
            @click="activeTab = 'pending'"
            class="flex-1 px-3 py-2 text-xs font-mono transition-colors"
            :class="activeTab === 'pending'
              ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'"
          >
            Pending ({{ pendingFeedback.length }})
          </button>
          <button
            @click="activeTab = 'archived'"
            class="flex-1 px-3 py-2 text-xs font-mono transition-colors"
            :class="activeTab === 'archived'
              ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'"
          >
            Archived ({{ archivedFeedback.length }})
          </button>
        </div>

        <div class="flex-1 overflow-auto">
          <template v-if="activeTab === 'pending'">
            <div
              v-for="file in pendingFeedback"
              :key="file.path"
              @click="selectFile(file.path)"
              class="px-3 py-2 cursor-pointer transition-colors border-b border-[var(--color-border-muted)]"
              :class="selectedFile === file.path
                ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)]'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-text)]'"
            >
              <div class="text-sm font-mono truncate">{{ getSummary(file.name) }}</div>
              <div class="text-xs text-[var(--color-text-subtle)] mt-0.5">{{ formatDate(file.name) }}</div>
            </div>
            <div v-if="pendingFeedback.length === 0" class="px-3 py-4 text-sm text-[var(--color-text-subtle)] text-center">
              No pending feedback
            </div>
          </template>
          <template v-else>
            <div
              v-for="file in archivedFeedback"
              :key="file.path"
              @click="selectFile('feedback/archive/' + file.name)"
              class="px-3 py-2 cursor-pointer transition-colors border-b border-[var(--color-border-muted)]"
              :class="selectedFile === 'feedback/archive/' + file.name
                ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)]'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-text)]'"
            >
              <div class="text-sm font-mono truncate">{{ getSummary(file.name) }}</div>
              <div class="text-xs text-[var(--color-text-subtle)] mt-0.5">{{ formatDate(file.name) }}</div>
            </div>
            <div v-if="archivedFeedback.length === 0" class="px-3 py-4 text-sm text-[var(--color-text-subtle)] text-center">
              No archived feedback
            </div>
          </template>
        </div>
      </div>

      <!-- Content viewer -->
      <div
        class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] overflow-hidden flex-col"
        :class="selectedFile ? 'flex flex-1' : 'hidden md:flex md:flex-1'"
      >
        <template v-if="selectedFile">
          <div class="px-4 py-2 border-b border-[var(--color-border)] flex items-center gap-3">
            <button
              @click="selectedFile = null"
              class="md:hidden text-xs font-mono text-[var(--color-accent)] hover:underline"
            >
              ← Back
            </button>
            <span class="text-sm font-mono text-[var(--color-text-muted)] truncate">{{ selectedFile }}</span>
          </div>
          <div class="flex-1 overflow-auto p-4">
            <div v-if="parsedYaml" class="space-y-4">
              <!-- Summary -->
              <div v-if="parsedYaml.summary">
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-1">Summary</div>
                <div class="text-sm text-[var(--color-text)] bg-[var(--color-bg)] rounded p-3">
                  {{ parsedYaml.summary }}
                </div>
              </div>

              <!-- Priority -->
              <div v-if="parsedYaml.priority" class="flex items-center gap-2">
                <span class="text-xs text-[var(--color-text-subtle)] font-mono">Priority:</span>
                <span
                  class="px-2 py-0.5 text-xs font-mono rounded"
                  :style="{
                    backgroundColor: getPriorityStyle(parsedYaml.priority).bg,
                    color: getPriorityStyle(parsedYaml.priority).text
                  }"
                >
                  {{ parsedYaml.priority.toUpperCase() }}
                </span>
              </div>

              <!-- Timestamp -->
              <div v-if="parsedYaml.meta?.timestamp" class="text-xs text-[var(--color-text-subtle)]">
                Created: {{ parsedYaml.meta.timestamp }}
              </div>

              <!-- Raw YAML -->
              <details class="group">
                <summary class="text-xs text-[var(--color-text-subtle)] font-mono cursor-pointer hover:text-[var(--color-text-muted)]">
                  Raw YAML
                </summary>
                <pre class="text-xs font-mono p-3 rounded bg-[var(--color-bg)] text-[var(--color-text)] overflow-auto whitespace-pre-wrap mt-2">{{ fileContent }}</pre>
              </details>
            </div>
            <pre v-else class="text-xs font-mono text-[var(--color-text)] whitespace-pre-wrap">{{ fileContent }}</pre>
          </div>
        </template>
        <div v-else class="flex-1 flex items-center justify-center text-[var(--color-text-subtle)]">
          Select a feedback item to view
        </div>
      </div>
    </div>
  </div>
</template>
