<template>
  <Popover>
    <PopoverTrigger as-child>
      <button
        type="button"
        class="flex size-12 cursor-pointer items-center justify-center rounded-xl text-rail-muted transition-colors hover:bg-white/10 hover:text-white"
        aria-label="Appearance"
        title="Appearance"
      >
        <component :is="icons[currentTheme]" class="size-5" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent side="right" align="end" class="flex w-auto flex-col gap-2 p-2.5">
      <ThemeChoices />
      <span class="max-w-60 px-0.5 text-xs text-ink-soft">
        Remembered on this device. System follows your device's light or dark setting.
      </span>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { MonitorIcon, MoonIcon, SunIcon } from '@lucide/vue'
import ThemeChoices from '@/components/shared/ThemeChoices.vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { currentTheme } from '@/lib/theme'

const icons = { system: MonitorIcon, light: SunIcon, dark: MoonIcon }
</script>
