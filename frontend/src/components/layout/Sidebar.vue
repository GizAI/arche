<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { computed } from 'vue'

defineProps<{
  collapsed: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

const route = useRoute()

const navItems = [
  { path: '/', name: 'Dashboard', icon: '◉' },
  { path: '/logs', name: 'Logs', icon: '▤' },
  { path: '/journals', name: 'Journals', icon: '▦' },
  { path: '/plans', name: 'Plans', icon: '▧' },
  { path: '/feedback', name: 'Feedback', icon: '▨' },
  { path: '/settings', name: 'Settings', icon: '⚙' },
]

const isActive = (path: string) => route.path === path
</script>

<template>
  <aside
    class="bg-[var(--color-bg-subtle)] border-r border-[var(--color-border)] flex flex-col transition-all duration-200"
    :class="collapsed ? 'w-16' : 'w-56'"
  >
    <!-- Header -->
    <div class="h-12 flex items-center justify-between px-4 border-b border-[var(--color-border)]">
      <span v-if="!collapsed" class="font-mono text-[var(--color-accent)] font-bold tracking-wider">
        ARCHE
      </span>
      <button
        @click="emit('toggle')"
        class="w-6 h-6 flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
      >
        {{ collapsed ? '▶' : '◀' }}
      </button>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 py-2">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-4 py-2 mx-2 rounded transition-colors"
        :class="[
          isActive(item.path)
            ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)]'
            : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-text)]'
        ]"
      >
        <span class="text-lg">{{ item.icon }}</span>
        <span v-if="!collapsed" class="text-sm">{{ item.name }}</span>
      </RouterLink>
    </nav>

    <!-- Footer -->
    <div class="p-4 border-t border-[var(--color-border)]">
      <div v-if="!collapsed" class="text-xs text-[var(--color-text-subtle)] font-mono">
        v0.1.0
      </div>
    </div>
  </aside>
</template>
