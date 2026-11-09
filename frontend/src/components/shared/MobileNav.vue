<template>
  <!-- Phones: the rail becomes a dark tab bar at the bottom. -->
  <nav
    class="md:hidden shrink-0 grid grid-cols-4 bg-ink pb-[env(safe-area-inset-bottom)]"
    aria-label="Main"
  >
    <RouterLink v-for="item in navItems" :key="item.to" v-slot="{ href, navigate, isActive }" :to="item.to" custom>
      <a
        :href="href"
        :aria-current="isActive ? 'page' : undefined"
        class="relative flex min-h-14 flex-col items-center justify-center gap-1 py-2 text-[11px]"
        :class="isActive ? 'font-semibold text-white' : 'font-medium text-rail-muted'"
        @click="navigate"
      >
        <span v-if="isActive" class="absolute top-0 left-1/2 h-0.5 w-10 -translate-x-1/2 rounded-full bg-paper" aria-hidden="true" />
        <component :is="item.icon" class="size-5" aria-hidden="true" />
        {{ item.label }}
        <span
          v-if="item.to === '/downloads' && activeDownloads > 0"
          class="absolute top-1 left-1/2 ml-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-rail-badge px-1 text-[10px] font-bold text-ink"
          :aria-label="`${activeDownloads} active`"
        >{{ activeDownloads }}</span>
      </a>
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { navItems } from './navItems'

defineProps<{ activeDownloads: number }>()
</script>
