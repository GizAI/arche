<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useFilesStore } from '@/stores/files'
import { storeToRefs } from 'pinia'
import yaml from 'yaml'

const filesStore = useFilesStore()
const { tree } = storeToRefs(filesStore)

const selectedFile = ref<string | null>(null)
const fileContent = ref<string>('')
const parsedYaml = ref<any>(null)

const plans = computed(() => filesStore.getFilesByDir('plan'))

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

function getTitle(filename: string): string {
  const match = filename.match(/^\d{8}-\d{4}-(.+)\.yaml$/)
  return match ? match[1]!.replace(/-/g, ' ') : filename
}

function getStatusStyle(state: string): { bg: string; text: string } {
  const statusColors: Record<string, { bg: string; text: string }> = {
    todo: { bg: 'rgba(163, 163, 163, 0.1)', text: 'var(--color-text-muted)' },
    doing: { bg: 'rgba(234, 179, 8, 0.1)', text: 'var(--color-warning)' },
    done: { bg: 'rgba(34, 197, 94, 0.1)', text: 'var(--color-success)' },
    blocked: { bg: 'rgba(239, 68, 68, 0.1)', text: 'var(--color-error)' },
  }
  return statusColors[state] ?? { bg: 'rgba(163, 163, 163, 0.1)', text: 'var(--color-text-muted)' }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-mono text-[var(--color-text)]">Plans</h1>
      <button
        @click="filesStore.fetchTree()"
        class="px-3 py-1.5 text-xs font-mono rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] border border-[var(--color-border)] hover:text-[var(--color-text)] transition-colors"
      >
        Refresh
      </button>
    </div>

    <div class="flex-1 flex flex-col md:flex-row gap-4 min-h-0">
      <!-- File list -->
      <div
        class="bg-[var(--color-bg-subtle)] rounded-lg border border-[var(--color-border)] overflow-hidden flex flex-col"
        :class="selectedFile ? 'hidden md:flex md:w-72' : 'flex-1 md:flex-none md:w-72'"
      >
        <div class="px-3 py-2 border-b border-[var(--color-border)] text-xs font-mono text-[var(--color-text-muted)]">
          {{ plans.length }} plan{{ plans.length === 1 ? '' : 's' }}
        </div>
        <div class="flex-1 overflow-auto">
          <div
            v-for="file in plans"
            :key="file.path"
            @click="selectFile(file.path)"
            class="px-3 py-2 cursor-pointer transition-colors border-b border-[var(--color-border-muted)]"
            :class="selectedFile === file.path
              ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)]'
              : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-text)]'"
          >
            <div class="text-sm font-mono truncate">{{ getTitle(file.name) }}</div>
            <div class="text-xs text-[var(--color-text-subtle)] mt-0.5">{{ formatDate(file.name) }}</div>
          </div>
          <div v-if="plans.length === 0" class="px-3 py-4 text-sm text-[var(--color-text-subtle)] text-center">
            No plans yet
          </div>
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
            <!-- Parsed plan view -->
            <div v-if="parsedYaml" class="space-y-4">
              <!-- Goal -->
              <div v-if="parsedYaml.goal">
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-1">Goal</div>
                <div class="text-sm text-[var(--color-accent)] bg-[var(--color-bg)] rounded p-3 font-mono">
                  {{ parsedYaml.goal }}
                </div>
              </div>

              <!-- Architecture notes -->
              <div v-if="parsedYaml.architecture_notes">
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-1">Architecture Notes</div>
                <pre class="text-xs text-[var(--color-text-muted)] bg-[var(--color-bg)] rounded p-3 whitespace-pre-wrap">{{ parsedYaml.architecture_notes }}</pre>
              </div>

              <!-- Items/Tasks -->
              <div v-if="parsedYaml.items?.length">
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-2">Tasks</div>
                <div class="space-y-2">
                  <div
                    v-for="item in parsedYaml.items"
                    :key="item.id"
                    class="bg-[var(--color-bg)] rounded p-3 border border-[var(--color-border-muted)]"
                  >
                    <div class="flex items-start gap-3">
                      <!-- Status badge -->
                      <span
                        class="px-2 py-0.5 text-xs font-mono rounded shrink-0 mt-0.5"
                        :style="{
                          backgroundColor: getStatusStyle(item.state).bg,
                          color: getStatusStyle(item.state).text
                        }"
                      >
                        {{ item.state?.toUpperCase() || 'TODO' }}
                      </span>
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2">
                          <span class="text-xs text-[var(--color-text-subtle)] font-mono">{{ item.id }}</span>
                          <span v-if="item.priority" class="text-xs text-[var(--color-warning)]">{{ item.priority }}</span>
                        </div>
                        <div class="text-sm text-[var(--color-text)] mt-0.5">{{ item.title }}</div>
                        <pre v-if="item.details" class="text-xs text-[var(--color-text-muted)] mt-2 whitespace-pre-wrap">{{ item.details }}</pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Raw YAML -->
              <div>
                <details class="group">
                  <summary class="text-xs text-[var(--color-text-subtle)] font-mono mb-1 cursor-pointer hover:text-[var(--color-text-muted)]">
                    Raw YAML
                  </summary>
                  <pre class="text-xs font-mono p-3 rounded bg-[var(--color-bg)] text-[var(--color-text)] overflow-auto whitespace-pre-wrap mt-2">{{ fileContent }}</pre>
                </details>
              </div>
            </div>

            <!-- Plain text fallback -->
            <pre v-else class="text-xs font-mono text-[var(--color-text)] whitespace-pre-wrap">{{ fileContent }}</pre>
          </div>
        </template>
        <div v-else class="flex-1 flex items-center justify-center text-[var(--color-text-subtle)]">
          Select a plan to view
        </div>
      </div>
    </div>
  </div>
</template>
