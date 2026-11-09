<template>
  <!-- dvh: the height left by the phone browser's own toolbars. Below md the
       sidebar becomes a bottom tab bar and Downloads becomes a tab. -->
  <div class="flex flex-col md:flex-row h-dvh bg-background text-foreground overflow-hidden">
    <AppSidebar
      :active-downloads="activeCount"
      :downloads-open="showDownloads"
      @toggle-downloads="showDownloads = !showDownloads"
    />
    <main class="flex-1 flex min-w-0 min-h-0 overflow-hidden">
      <RouterView />
    </main>
    <DownloadQueuePanel v-if="showDownloads && isDesktop" @close="showDownloads = false" />
    <MobileNav :active-downloads="activeCount" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import AppSidebar from '@/components/shared/AppSidebar.vue'
import MobileNav from '@/components/shared/MobileNav.vue'
import DownloadQueuePanel from '@/components/downloads/DownloadQueuePanel.vue'
import { useDownloadsStore } from '@/stores/downloads'
import { useSettingsStore } from '@/stores/settings'
import { useDownloadProgress } from '@/composables/useWebSocket'

const showDownloads = ref(false)
const isDesktop = useMediaQuery('(min-width: 768px)')
const downloadsStore = useDownloadsStore()
const settingsStore = useSettingsStore()
useDownloadProgress((event) => downloadsStore.handleProgressEvent(event))
settingsStore.load()

const activeCount = computed(() => downloadsStore.activeJobs().length)
</script>
