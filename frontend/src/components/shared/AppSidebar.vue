<template>
  <nav class="flex flex-col w-56 h-screen bg-gray-900 text-gray-100 p-4 gap-1 shrink-0">
    <div class="text-xl font-bold mb-6 px-2">Libation</div>

    <RouterLink
      v-for="item in navItems"
      :key="item.to"
      :to="item.to"
      class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm hover:bg-gray-700 transition-colors"
      activeClass="bg-gray-700"
    >
      <span class="w-5 text-center">{{ item.icon }}</span>
      {{ item.label }}
    </RouterLink>

    <div class="mt-auto">
      <div v-if="activeCount > 0" class="px-3 py-2 text-xs text-gray-400">
        {{ activeCount }} download{{ activeCount === 1 ? '' : 's' }} active
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'

const downloadsStore = useDownloadsStore()
const activeCount = computed(() => downloadsStore.activeJobs().length)

const navItems = [
  { to: '/library', label: 'Library', icon: '📚' },
  { to: '/downloads', label: 'Downloads', icon: '⬇️' },
  { to: '/accounts', label: 'Accounts', icon: '👤' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]
</script>
