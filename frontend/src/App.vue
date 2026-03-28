<template>
  <div class="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
    <AppSidebar />
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import AppSidebar from '@/components/shared/AppSidebar.vue'
import { useDownloadsStore } from '@/stores/downloads'
import { useDownloadProgress } from '@/composables/useWebSocket'

const downloadsStore = useDownloadsStore()
useDownloadProgress((event) => downloadsStore.handleProgressEvent(event))
</script>
