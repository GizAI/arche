<script setup lang="ts">
import { ref, onMounted, provide } from 'vue'
import axios from 'axios'
import AppShell from '@/components/layout/AppShell.vue'
import SetupWizard from '@/components/SetupWizard.vue'
import LoginScreen from '@/components/LoginScreen.vue'
import { useTheme } from '@/composables/useTheme'

// Enable cookies for all requests
axios.defaults.withCredentials = true

const { initTheme } = useTheme()

const setupComplete = ref(false)
const authenticated = ref(false)
const requiresAuth = ref(false)
const loading = ref(true)
const loginScreenRef = ref<InstanceType<typeof LoginScreen> | null>(null)

const checkAuthStatus = async () => {
  try {
    await axios.get('/api/status')
    authenticated.value = true
  } catch (err: any) {
    if (err.response?.status === 401) {
      requiresAuth.value = true
      authenticated.value = false
    }
  } finally {
    loading.value = false
  }
}

const handleSetupComplete = () => {
  setupComplete.value = true
  checkAuthStatus()
}

const handleLogin = async (password: string) => {
  try {
    await axios.post('/api/auth/login', { password })
    authenticated.value = true
    requiresAuth.value = false
  } catch {
    loginScreenRef.value?.handleError('Invalid password')
  }
}

const logout = async () => {
  try {
    await axios.post('/api/auth/logout')
  } catch {
    // Ignore
  }
  authenticated.value = false
  requiresAuth.value = true
}

provide('logout', logout)

onMounted(async () => {
  initTheme()
  await checkAuthStatus()
})
</script>

<template>
  <SetupWizard @complete="handleSetupComplete" />

  <template v-if="setupComplete">
    <LoginScreen
      v-if="requiresAuth && !authenticated"
      ref="loginScreenRef"
      @login="handleLogin"
    />

    <AppShell v-if="authenticated || (!requiresAuth && !loading)">
      <RouterView />
    </AppShell>
  </template>
</template>
