<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'
import StatusBar from './StatusBar.vue'

const sidebarCollapsed = ref(false)
</script>

<template>
  <div class="h-screen flex flex-col bg-[var(--color-bg)]">
    <!-- Status bar at top -->
    <StatusBar />

    <div class="flex-1 flex overflow-hidden">
      <!-- Sidebar -->
      <Sidebar
        :collapsed="sidebarCollapsed"
        @toggle="sidebarCollapsed = !sidebarCollapsed"
      />

      <!-- Main content -->
      <main class="flex-1 overflow-auto p-6">
        <slot />
      </main>
    </div>
  </div>
</template>
