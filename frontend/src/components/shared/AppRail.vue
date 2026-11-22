<template>
  <!-- Desktop navigation: the design's dark 72 px rail. Phones get MobileNav instead. -->
  <nav
    aria-label="Main"
    class="hidden md:flex w-[72px] shrink-0 flex-col items-center gap-1.5 bg-rail py-4"
  >
    <span class="mb-3.5 flex size-10 items-center justify-center rounded-[10px] bg-white" title="Libera">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#121418" stroke-width="2.2"
           stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="Libera">
        <rect x="4" y="11" width="16" height="10" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 7.5-2" />
      </svg>
    </span>
    <RouterLink v-for="item in navItems" :key="item.to" v-slot="{ href, navigate, isActive }" :to="item.to" custom>
      <a
        :href="href"
        :aria-current="isActive ? 'page' : undefined"
        :aria-label="item.to === '/downloads' && activeDownloads ? `Downloads, ${activeDownloads} active` : item.label"
        :title="item.label"
        class="relative flex size-12 items-center justify-center rounded-xl transition-colors"
        :class="isActive ? 'bg-paper text-ink dark:bg-white/15 dark:text-white' :'text-rail-muted hover:bg-white/10 hover:text-white'"
        @click="navigate"
      >
        <component :is="item.icon" class="size-5" aria-hidden="true" />
        <span
          v-if="item.to === '/downloads' && activeDownloads > 0"
          class="absolute right-2 top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-rail-badge px-1 text-[10px] font-bold text-rail"
          aria-hidden="true"
        >{{ activeDownloads }}</span>
      </a>
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { navItems } from './navItems'

defineProps<{ activeDownloads: number }>()
</script>
