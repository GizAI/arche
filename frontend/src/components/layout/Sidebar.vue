<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { inject } from 'vue'

const props = defineProps<{
  collapsed: boolean
  mobileOpen?: boolean
  isMobile?: boolean
}>()

const emit = defineEmits<{
  toggle: []
  close: []
}>()

const route = useRoute()
const logout = inject<() => void>('logout')

const navItems = [
  { path: '/', name: 'Dashboard', icon: '◉' },
  { path: '/interactive', name: 'Interactive', icon: '⌘' },
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
    class="bg-[var(--color-bg-subtle)] border-r border-[var(--color-border)] flex flex-col transition-all duration-300"
    :class="[
      isMobile
        ? 'fixed top-10 bottom-0 left-0 z-50 w-64 transform'
        : collapsed ? 'w-16' : 'w-56',
      isMobile && !mobileOpen ? '-translate-x-full' : 'translate-x-0'
    ]"
  >
    <!-- Header -->
    <div class="h-12 flex items-center justify-between px-4 border-b border-[var(--color-border)]">
      <span v-if="!collapsed || isMobile" class="font-mono text-[var(--color-accent)] font-bold tracking-wider">
        ARCHE
      </span>
      <button
        v-if="!isMobile"
        @click="emit('toggle')"
        class="w-6 h-6 flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
      >
        {{ collapsed ? '▶' : '◀' }}
      </button>
      <button
        v-else
        @click="emit('close')"
        class="w-6 h-6 flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
      >
        ✕
      </button>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 py-2 overflow-auto">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        @click="isMobile && emit('close')"
        class="flex items-center gap-3 px-4 py-2 mx-2 rounded transition-colors"
        :class="[
          isActive(item.path)
            ? 'bg-[var(--color-bg-elevated)] text-[var(--color-accent)]'
            : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-text)]'
        ]"
      >
        <span class="text-lg">{{ item.icon }}</span>
        <span v-if="!collapsed || isMobile" class="text-sm">{{ item.name }}</span>
      </RouterLink>
    </nav>

    <!-- Footer -->
    <div class="p-4 border-t border-[var(--color-border)] space-y-2">
      <button
        v-if="logout"
        @click="logout"
        class="flex items-center gap-3 w-full px-2 py-1.5 rounded text-[var(--color-text-muted)] hover:bg-[var(--color-bg-muted)] hover:text-[var(--color-error)] transition-colors"
      >
        <span class="text-lg">⏻</span>
        <span v-if="!collapsed || isMobile" class="text-sm">Logout</span>
      </button>
      <div v-if="!collapsed || isMobile" class="text-xs text-[var(--color-text-subtle)] font-mono">
        v0.1.0
      </div>
    </div>
  </aside>
</template>
