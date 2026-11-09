<template>
  <nav class="hidden md:flex flex-col w-64 h-full bg-sidebar text-sidebar-foreground border-r border-sidebar-border shrink-0">
    <!-- Logo -->
    <div class="p-6">
      <h1 class="font-semibold text-xl">Libation Web</h1>
      <p class="text-sm text-muted-foreground mt-0.5">Audiobook Manager</p>
    </div>

    <Separator />

    <!-- Nav -->
    <div class="flex-1 px-3 py-4 space-y-1">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        active-class="bg-sidebar-accent text-sidebar-accent-foreground"
      >
        <component :is="item.icon" class="h-4 w-4 shrink-0" />
        {{ item.label }}
      </RouterLink>

      <!-- Opens the download queue panel beside the current page. -->
      <button
        type="button"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        :class="downloadsOpen ? 'bg-sidebar-accent text-sidebar-accent-foreground' : ''"
        :aria-pressed="downloadsOpen"
        @click="emit('toggle-downloads')"
      >
        <DownloadIcon class="h-4 w-4 shrink-0" />
        Downloads
        <span
          v-if="activeDownloads > 0"
          class="ml-auto bg-primary text-primary-foreground text-xs font-bold min-w-5 h-5 px-1 rounded-full flex items-center justify-center"
          :aria-label="`${activeDownloads} active`"
        >{{ activeDownloads }}</span>
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { defineComponent, h } from 'vue'
import { DownloadIcon } from '@lucide/vue'
import { Separator } from '@/components/ui/separator'

defineProps<{ activeDownloads: number; downloadsOpen: boolean }>()
const emit = defineEmits<{ 'toggle-downloads': [] }>()

const LibraryIcon = defineComponent({
  render: () => h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
    h('path', { d: 'm16 6 4 14' }),
    h('path', { d: 'M12 6v14' }),
    h('path', { d: 'M8 8v12' }),
    h('path', { d: 'M4 4v16' }),
  ]),
})

const UsersIcon = defineComponent({
  render: () => h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
    h('path', { d: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2' }),
    h('circle', { cx: '9', cy: '7', r: '4' }),
    h('path', { d: 'M22 21v-2a4 4 0 0 0-3-3.87' }),
    h('path', { d: 'M16 3.13a4 4 0 0 1 0 7.75' }),
  ]),
})

const SettingsIcon = defineComponent({
  render: () => h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
    h('path', { d: 'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z' }),
    h('circle', { cx: '12', cy: '12', r: '3' }),
  ]),
})

const navItems = [
  { to: '/library', label: 'Library', icon: LibraryIcon },
  { to: '/accounts', label: 'Accounts', icon: UsersIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]
</script>
