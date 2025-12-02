<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Sidebar from './Sidebar.vue'
import StatusBar from './StatusBar.vue'

const sidebarCollapsed = ref(false)
const sidebarOpen = ref(false)
const isMobile = ref(false)

// Check if mobile
const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    sidebarOpen.value = false
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const toggleSidebar = () => {
  if (isMobile.value) {
    sidebarOpen.value = !sidebarOpen.value
  } else {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
}

const closeSidebar = () => {
  if (isMobile.value) {
    sidebarOpen.value = false
  }
}
</script>

<template>
  <div class="h-screen flex flex-col bg-[var(--color-bg)]">
    <!-- Status bar at top -->
    <StatusBar />

    <div class="flex-1 flex overflow-hidden relative">
      <!-- Mobile overlay -->
      <div
        v-if="isMobile && sidebarOpen"
        @click="closeSidebar"
        class="fixed inset-0 bg-black/50 z-40 md:hidden backdrop-blur-sm"
      />

      <!-- Sidebar -->
      <Sidebar
        :collapsed="sidebarCollapsed"
        :mobile-open="sidebarOpen"
        :is-mobile="isMobile"
        @toggle="toggleSidebar"
        @close="closeSidebar"
      />

      <!-- Main content -->
      <main class="flex-1 overflow-auto p-4 md:p-6" :class="{ 'pb-20': isMobile }">
        <slot />
      </main>

      <!-- Mobile bottom nav -->
      <nav v-if="isMobile" class="fixed bottom-0 left-0 right-0 bg-[var(--color-bg-subtle)] border-t border-[var(--color-border)] z-30 safe-area-bottom">
        <div class="flex justify-around items-center h-16">
          <button
            @click="toggleSidebar"
            class="flex flex-col items-center justify-center gap-1 px-4 py-2 text-[var(--color-text-muted)] active:text-[var(--color-accent)] transition-colors"
          >
            <span class="text-lg">☰</span>
            <span class="text-xs font-mono">Menu</span>
          </button>
          <RouterLink
            to="/"
            @click="closeSidebar"
            class="flex flex-col items-center justify-center gap-1 px-4 py-2 text-[var(--color-text-muted)] active:text-[var(--color-accent)] transition-colors"
          >
            <span class="text-lg">◉</span>
            <span class="text-xs font-mono">Home</span>
          </RouterLink>
          <RouterLink
            to="/logs"
            @click="closeSidebar"
            class="flex flex-col items-center justify-center gap-1 px-4 py-2 text-[var(--color-text-muted)] active:text-[var(--color-accent)] transition-colors"
          >
            <span class="text-lg">▤</span>
            <span class="text-xs font-mono">Logs</span>
          </RouterLink>
          <RouterLink
            to="/feedback"
            @click="closeSidebar"
            class="flex flex-col items-center justify-center gap-1 px-4 py-2 text-[var(--color-text-muted)] active:text-[var(--color-accent)] transition-colors"
          >
            <span class="text-lg">▨</span>
            <span class="text-xs font-mono">Feedback</span>
          </RouterLink>
        </div>
      </nav>
    </div>
  </div>
</template>

<style scoped>
.safe-area-bottom {
  padding-bottom: env(safe-area-inset-bottom);
}
</style>
