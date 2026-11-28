<template>
  <div role="radiogroup" aria-label="Appearance" class="flex overflow-hidden rounded-[10px] border border-line bg-surface">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      class="flex h-10 flex-1 cursor-pointer items-center justify-center gap-2 px-3 text-sm"
      :class="currentTheme === option.value ? 'bg-ink font-semibold text-on-ink' : 'font-medium text-ink hover:bg-paper'"
      :aria-checked="currentTheme === option.value"
      @click="setThemeChoice(option.value)"
    >
      <component :is="option.icon" class="size-4" aria-hidden="true" />{{ option.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { MonitorIcon, MoonIcon, SunIcon } from '@lucide/vue'
import { currentTheme, setThemeChoice } from '@/lib/theme'

const options = [
  { value: 'system', label: 'System', icon: MonitorIcon },
  { value: 'light', label: 'Light', icon: SunIcon },
  { value: 'dark', label: 'Dark', icon: MoonIcon },
] as const
</script>
