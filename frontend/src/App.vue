<template>
  <div class="flex h-screen bg-background text-foreground overflow-hidden">
    <AppSidebar />
    <main class="flex-1 flex min-w-0 overflow-hidden">
      <RouterView />
    </main>
    <DownloadQueuePanel v-if="showDownloads" @close="showDownloads = false" />

    <!-- Floating Downloads Button -->
    <button
      class="fixed top-5 right-6 z-50 flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2.5 rounded-full shadow-lg hover:opacity-90 transition-opacity font-medium text-sm"
      @click="showDownloads = !showDownloads"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" x2="12" y1="15" y2="3"/>
      </svg>
      Downloads
      <span
        v-if="activeCount > 0"
        class="bg-white text-primary text-xs font-bold min-w-5 h-5 rounded-full flex items-center justify-center px-1"
      >{{ activeCount }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import AppSidebar from '@/components/shared/AppSidebar.vue'
import DownloadQueuePanel from '@/components/downloads/DownloadQueuePanel.vue'
import { useDownloadsStore } from '@/stores/downloads'
import { useSettingsStore } from '@/stores/settings'
import { useDownloadProgress } from '@/composables/useWebSocket'

const showDownloads = ref(false)
const downloadsStore = useDownloadsStore()
const settingsStore = useSettingsStore()
useDownloadProgress((event) => downloadsStore.handleProgressEvent(event))
settingsStore.load()

const activeCount = computed(() => downloadsStore.activeJobs().length)
</script>
