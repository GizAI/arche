<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTheme } from '@/composables/useTheme'

const emit = defineEmits<{
  login: [password: string]
}>()

const { theme, toggleTheme, initTheme } = useTheme()

const password = ref('')
const error = ref('')
const submitting = ref(false)

const submit = async () => {
  if (!password.value) {
    error.value = 'Please enter password'
    return
  }
  error.value = ''
  submitting.value = true
  emit('login', password.value)
}

const handleError = (msg: string) => {
  error.value = msg
  submitting.value = false
}

onMounted(() => {
  initTheme()
})

defineExpose({ handleError })
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg)]/95 backdrop-blur-sm">
    <!-- Theme toggle -->
    <button
      @click="toggleTheme"
      class="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors rounded border border-[var(--color-border)] bg-[var(--color-bg-subtle)]"
    >
      {{ theme === 'dark' ? '☀' : '☽' }}
    </button>

    <!-- Login card -->
    <div class="card-layered rounded-lg border border-[var(--color-border)] p-8 max-w-md w-full mx-4 shadow-2xl">
      <div class="space-y-6">
        <!-- Header -->
        <div class="text-center">
          <h1 class="text-2xl font-mono text-[var(--color-accent)] font-bold tracking-wider mb-2">ARCHE</h1>
          <p class="text-sm text-[var(--color-text-muted)]">
            Enter password to continue
          </p>
        </div>

        <!-- Form -->
        <form @submit.prevent="submit" class="space-y-4">
          <div>
            <label class="block text-sm font-mono text-[var(--color-text-muted)] mb-2">
              Password
            </label>
            <input
              v-model="password"
              type="password"
              placeholder="Enter password"
              autofocus
              class="w-full px-3 py-2 bg-[var(--color-bg-muted)] border border-[var(--color-border)] rounded text-[var(--color-text)] font-mono text-sm focus:outline-none focus:border-[var(--color-accent)] transition-colors"
            />
          </div>

          <div v-if="error" class="text-sm text-[var(--color-error)] font-mono">
            {{ error }}
          </div>

          <button
            type="submit"
            :disabled="submitting"
            class="w-full px-4 py-2 bg-[var(--color-accent)] text-white font-mono text-sm rounded hover:bg-[var(--color-accent-muted)] transition-colors disabled:opacity-50"
          >
            {{ submitting ? 'Logging in...' : 'Login' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
