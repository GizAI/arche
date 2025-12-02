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

const journals = computed(() => filesStore.getFilesByDir('journal'))

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
  // Extract date from filename like 20251203-0027-plan-daemon-webui.yaml
  const match = filename.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/)
  if (!match) return filename
  const [, year, month, day, hour, minute] = match
  return `${year}-${month}-${day} ${hour}:${minute}`
}

function getTitle(filename: string): string {
  // Extract title part after the timestamp
  const match = filename.match(/^\d{8}-\d{4}-(.+)\.yaml$/)
  return match ? match[1]!.replace(/-/g, ' ') : filename
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-mono text-[var(--color-text)]">Journals</h1>
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
          {{ journals.length }} journal{{ journals.length === 1 ? '' : 's' }}
        </div>
        <div class="flex-1 overflow-auto">
          <div
            v-for="file in journals"
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
          <div v-if="journals.length === 0" class="px-3 py-4 text-sm text-[var(--color-text-subtle)] text-center">
            No journals yet
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
            <!-- Parsed YAML view -->
            <div v-if="parsedYaml" class="space-y-4">
              <!-- Turn info -->
              <div v-if="parsedYaml.turn" class="flex items-center gap-2">
                <span class="text-xs text-[var(--color-text-subtle)] font-mono">Turn</span>
                <span class="text-lg font-mono text-[var(--color-accent)]">{{ parsedYaml.turn }}</span>
              </div>

              <!-- Task -->
              <div v-if="parsedYaml.task">
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-1">Task</div>
                <div class="text-sm text-[var(--color-text)] bg-[var(--color-bg)] rounded p-3">
                  {{ parsedYaml.task }}
                </div>
              </div>

              <!-- Files -->
              <div v-if="parsedYaml.files?.length">
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-1">Files Changed</div>
                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="file in parsedYaml.files"
                    :key="file"
                    class="text-xs font-mono px-2 py-1 rounded bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                  >
                    {{ file }}
                  </span>
                </div>
              </div>

              <!-- Raw YAML -->
              <div>
                <div class="text-xs text-[var(--color-text-subtle)] font-mono mb-1">Raw YAML</div>
                <pre class="text-xs font-mono p-3 rounded bg-[var(--color-bg)] text-[var(--color-text)] overflow-auto whitespace-pre-wrap">{{ fileContent }}</pre>
              </div>
            </div>

            <!-- Plain text fallback -->
            <pre v-else class="text-xs font-mono text-[var(--color-text)] whitespace-pre-wrap">{{ fileContent }}</pre>
          </div>
        </template>
        <div v-else class="flex-1 flex items-center justify-center text-[var(--color-text-subtle)]">
          Select a journal to view
        </div>
      </div>
    </div>
  </div>
</template>
