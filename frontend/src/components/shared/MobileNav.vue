<template>
  <!-- Bottom tab bar on phones; the sidebar takes over from md up. -->
  <nav
    class="md:hidden shrink-0 border-t bg-background grid grid-cols-4 pb-[env(safe-area-inset-bottom)]"
    aria-label="Main"
  >
    <RouterLink v-for="item in items" :key="item.to" v-slot="{ href, navigate, isActive }" :to="item.to" custom>
      <a
        :href="href"
        :aria-current="isActive ? 'page' : undefined"
        class="relative flex flex-col items-center justify-center gap-1 py-2 min-h-14 text-[11px]"
        :class="isActive ? 'text-foreground font-semibold' : 'text-muted-foreground font-medium'"
        @click="navigate"
      >
        <span
          v-if="isActive"
          class="absolute top-0 left-1/2 -translate-x-1/2 h-0.5 w-10 rounded-full bg-foreground"
          aria-hidden="true"
        />
        <component :is="item.icon" class="h-5 w-5" :stroke-width="isActive ? 2.5 : 2" aria-hidden="true" />
        {{ item.label }}
        <span
          v-if="item.to === '/downloads' && activeDownloads > 0"
          class="absolute top-1 left-1/2 ml-2 bg-primary text-primary-foreground text-[10px] font-bold min-w-4 h-4 px-1 rounded-full flex items-center justify-center"
          :aria-label="`${activeDownloads} active`"
        >{{ activeDownloads }}</span>
      </a>
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { DownloadIcon, LibraryIcon, SettingsIcon, UsersIcon } from '@lucide/vue'

defineProps<{ activeDownloads: number }>()

const items = [
  { to: '/library', label: 'Library', icon: LibraryIcon },
  { to: '/downloads', label: 'Downloads', icon: DownloadIcon },
  { to: '/accounts', label: 'Accounts', icon: UsersIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]
</script>
