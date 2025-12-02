<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useTheme } from '@/composables/useTheme'

const emit = defineEmits<{
  complete: []
}>()

const { theme, toggleTheme, initTheme } = useTheme()

const needsSetup = ref(false)
const loading = ref(true)
const password = ref('')
const confirmPassword = ref('')
const skipPassword = ref(false)
const error = ref('')
const submitting = ref(false)

const checkSetupStatus = async () => {
  try {
    const res = await axios.get('/api/setup/status')
    needsSetup.value = res.data.needs_setup
    if (!needsSetup.value) {
      emit('complete')
    }
  } catch (err) {
    console.error('Failed to check setup status:', err)
    // If we can't check, assume setup is not needed
    needsSetup.value = false
    emit('complete')
  } finally {
    loading.value = false
  }
}

const submitSetup = async () => {
  error.value = ''

  if (!skipPassword.value) {
    if (!password.value) {
      error.value = 'Please enter a password or choose to skip'
      return
    }
    if (password.value.length < 8) {
      error.value = 'Password must be at least 8 characters'
      return
    }
    if (password.value !== confirmPassword.value) {
      error.value = 'Passwords do not match'
      return
    }
  }

  submitting.value = true
  try {
    await axios.post('/api/setup/password', {
      password: skipPassword.value ? null : password.value,
    })
    emit('complete')
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'Setup failed'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  initTheme()
  checkSetupStatus()
})
</script>

<template>
  <div v-if="loading || needsSetup" class="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-bg)]/95 backdrop-blur-sm">
    <!-- Theme toggle -->
    <button
      @click="toggleTheme"
      class="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors rounded border border-[var(--color-border)] bg-[var(--color-bg-subtle)]"
    >
      {{ theme === 'dark' ? '☀' : '☽' }}
    </button>

    <!-- Loading state -->
    <div v-if="loading" class="text-center">
      <div class="animate-pulse text-[var(--color-text-muted)] font-mono">Loading...</div>
    </div>

    <!-- Setup wizard -->
    <div v-else class="card-layered rounded-lg border border-[var(--color-border)] p-8 max-w-md w-full mx-4 shadow-2xl">
      <div class="space-y-6">
        <!-- Header -->
        <div class="text-center">
          <h1 class="text-2xl font-mono text-[var(--color-text)] mb-2">Welcome to Arche</h1>
          <p class="text-sm text-[var(--color-text-muted)]">
            First-time setup: secure your daemon with a password
          </p>
        </div>

        <!-- Form -->
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-mono text-[var(--color-text-muted)] mb-2">
              Password (optional)
            </label>
            <input
              v-model="password"
              type="password"
              :disabled="skipPassword"
              placeholder="Enter password (min 8 characters)"
              class="w-full px-3 py-2 bg-[var(--color-bg-muted)] border border-[var(--color-border)] rounded text-[var(--color-text)] font-mono text-sm focus:outline-none focus:border-[var(--color-accent)] transition-colors disabled:opacity-50"
            />
          </div>

          <div v-if="!skipPassword">
            <label class="block text-sm font-mono text-[var(--color-text-muted)] mb-2">
              Confirm Password
            </label>
            <input
              v-model="confirmPassword"
              type="password"
              placeholder="Confirm password"
              class="w-full px-3 py-2 bg-[var(--color-bg-muted)] border border-[var(--color-border)] rounded text-[var(--color-text)] font-mono text-sm focus:outline-none focus:border-[var(--color-accent)] transition-colors"
            />
          </div>

          <div class="flex items-center gap-2">
            <input
              v-model="skipPassword"
              type="checkbox"
              id="skip-password"
              class="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg-muted)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
            />
            <label for="skip-password" class="text-sm text-[var(--color-text-muted)] font-mono">
              Skip password (not recommended for production)
            </label>
          </div>

          <div v-if="error" class="text-sm text-[var(--color-error)] font-mono">
            {{ error }}
          </div>
        </div>

        <!-- Actions -->
        <div class="flex gap-3">
          <button
            @click="submitSetup"
            :disabled="submitting"
            class="flex-1 px-4 py-2 bg-[var(--color-accent)] text-white font-mono text-sm rounded hover:bg-[var(--color-accent-muted)] transition-colors disabled:opacity-50"
          >
            {{ submitting ? 'Setting up...' : 'Continue' }}
          </button>
        </div>

        <!-- Info -->
        <div class="text-xs text-[var(--color-text-subtle)] font-mono text-center">
          Password will be stored in .arche/state.json
        </div>
      </div>
    </div>
  </div>
</template>
