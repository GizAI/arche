<script setup lang="ts">
import { ref, computed } from 'vue'
import type { SkillInfo } from '@/stores/interactive'

const props = defineProps<{
  available: SkillInfo[]
  loaded: string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  load: [skillName: string]
  unload: [skillName: string]
}>()

const isOpen = ref(false)

const unloadedSkills = computed(() =>
  props.available.filter(s => !props.loaded.includes(s.name))
)

function toggleSkill(skill: SkillInfo) {
  if (props.loaded.includes(skill.name)) {
    emit('unload', skill.name)
  } else {
    emit('load', skill.name)
  }
}
</script>

<template>
  <div class="skill-selector">
    <button
      class="skill-trigger"
      @click="isOpen = !isOpen"
      :disabled="disabled"
    >
      <span class="skill-icon">🎯</span>
      <span class="skill-label">Skills</span>
      <span v-if="loaded.length > 0" class="skill-count">{{ loaded.length }}</span>
      <span class="dropdown-arrow">{{ isOpen ? '▲' : '▼' }}</span>
    </button>

    <div v-if="isOpen" class="skill-dropdown">
      <div v-if="loaded.length > 0" class="skill-section">
        <div class="section-label">Loaded</div>
        <button
          v-for="skillName in loaded"
          :key="skillName"
          class="skill-item loaded"
          @click="emit('unload', skillName)"
        >
          <span class="skill-name">{{ skillName }}</span>
          <span class="remove-icon">×</span>
        </button>
      </div>

      <div v-if="unloadedSkills.length > 0" class="skill-section">
        <div class="section-label">Available</div>
        <button
          v-for="skill in unloadedSkills"
          :key="skill.name"
          class="skill-item"
          @click="emit('load', skill.name)"
          :title="skill.description"
        >
          <span class="skill-name">{{ skill.name }}</span>
          <span class="add-icon">+</span>
        </button>
      </div>

      <div v-if="available.length === 0" class="skill-empty">
        No skills available. Create skills in .arche/skills/
      </div>
    </div>

    <div v-if="isOpen" class="skill-backdrop" @click="isOpen = false" />
  </div>
</template>

<style scoped>
.skill-selector {
  position: relative;
}

.skill-trigger {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  background: var(--bg-color, #1a1a1a);
  color: var(--text-color, #e0e0e0);
  font-size: 0.875rem;
  cursor: pointer;
  transition: border-color 0.2s;
}

.skill-trigger:hover:not(:disabled) {
  border-color: var(--border-hover, #555);
}

.skill-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.skill-icon {
  font-size: 0.875rem;
}

.skill-label {
  font-weight: 500;
}

.skill-count {
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
  background: var(--accent-color, #5a67d8);
  color: white;
  font-size: 0.625rem;
  font-weight: 600;
}

.dropdown-arrow {
  font-size: 0.625rem;
  color: var(--text-muted, #666);
}

.skill-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 200px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  background: var(--bg-color, #1a1a1a);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 100;
}

.skill-section {
  padding: 0.5rem;
}

.skill-section + .skill-section {
  border-top: 1px solid var(--border-color, #333);
}

.section-label {
  padding: 0.25rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-muted, #666);
}

.skill-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-color, #e0e0e0);
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.skill-item:hover {
  background: var(--bg-hover, #252525);
}

.skill-item.loaded {
  background: var(--accent-bg, rgba(90, 103, 216, 0.1));
}

.skill-name {
  flex: 1;
}

.add-icon, .remove-icon {
  color: var(--text-muted, #666);
  font-size: 1rem;
}

.skill-item:hover .add-icon {
  color: var(--success-color, #10b981);
}

.skill-item:hover .remove-icon {
  color: var(--error-color, #ef4444);
}

.skill-empty {
  padding: 1rem;
  text-align: center;
  color: var(--text-muted, #666);
  font-size: 0.75rem;
}

.skill-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;
}
</style>
