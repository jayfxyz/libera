<template>
  <!-- Phones: the rail becomes a dark top bar with a hamburger menu in the top right corner. -->
  <header class="relative z-40 shrink-0 bg-rail pt-[env(safe-area-inset-top)] md:hidden">
    <div class="flex h-14 items-center justify-between pr-2 pl-4">
      <RouterLink to="/library" class="flex items-center gap-2.5 text-[15px] font-semibold text-white">
        <span class="flex size-8 items-center justify-center rounded-lg bg-white">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#121418" stroke-width="2.2"
               stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="4" y="11" width="16" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 7.5-2" />
          </svg>
        </span>
        Libera
      </RouterLink>
      <button
        type="button"
        class="relative flex size-11 items-center justify-center rounded-xl text-white active:bg-white/10"
        :aria-label="open ? 'Close menu' : activeDownloads ? `Open menu, ${activeDownloads} active downloads` : 'Open menu'"
        :aria-expanded="open"
        aria-controls="mobile-menu"
        @click="open = !open"
      >
        <component :is="open ? XIcon : MenuIcon" class="size-6" aria-hidden="true" />
        <span
          v-if="!open && activeDownloads > 0"
          class="absolute top-1.5 right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rail-badge px-1 text-[10px] font-bold text-rail"
          aria-hidden="true"
        >{{ activeDownloads }}</span>
      </button>
    </div>

    <template v-if="open">
      <div class="absolute inset-x-0 top-full h-dvh bg-black/40" aria-hidden="true" @click="open = false" />
      <nav
        id="mobile-menu"
        aria-label="Main"
        class="absolute inset-x-0 top-full flex flex-col gap-1 rounded-b-2xl bg-rail px-2 pt-1 pb-3 shadow-xl dark:border-b dark:border-line"
      >
        <RouterLink v-for="item in navItems" :key="item.to" v-slot="{ href, navigate, isActive }" :to="item.to" custom>
          <a
            :href="href"
            :aria-current="isActive ? 'page' : undefined"
            class="flex min-h-12 items-center gap-3 rounded-xl px-3 text-[15px]"
            :class="isActive ? 'bg-paper font-semibold text-ink dark:bg-white/15 dark:text-white' :'font-medium text-rail-muted active:bg-white/10'"
            @click="(e: MouseEvent) => { navigate(e); open = false }"
          >
            <component :is="item.icon" class="size-5" aria-hidden="true" />
            {{ item.label }}
            <span
              v-if="item.to === '/downloads' && activeDownloads > 0"
              class="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-rail-badge px-1.5 text-[11px] font-bold text-ink"
              :aria-label="`${activeDownloads} active`"
            >{{ activeDownloads }}</span>
          </a>
        </RouterLink>
        <div class="mt-1 flex flex-col gap-2 border-t border-bar-line px-3 pt-3">
          <span class="text-xs font-medium text-rail-muted">Appearance</span>
          <ThemeChoices />
        </div>
      </nav>
    </template>
  </header>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { MenuIcon, XIcon } from '@lucide/vue'
import ThemeChoices from './ThemeChoices.vue'
import { navItems } from './navItems'

defineProps<{ activeDownloads: number }>()

const open = ref(false)
const route = useRoute()
watch(() => route.fullPath, () => (open.value = false))

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>
