<template>
  <!-- Desktop: rail | page. Phones: top bar with a hamburger menu, page below. -->
  <div class="flex h-dvh flex-col overflow-hidden bg-paper text-ink md:flex-row">
    <AppRail :active-downloads="activeCount" />
    <MobileNav :active-downloads="activeCount" />
    <main class="flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppRail from '@/components/shared/AppRail.vue'
import MobileNav from '@/components/shared/MobileNav.vue'
import { useDownloadsStore } from '@/stores/downloads'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import { useDownloadProgress } from '@/composables/useWebSocket'

const downloads = useDownloadsStore()
const library = useLibraryStore()
const settings = useSettingsStore()

useDownloadProgress((event) => {
  downloads.handleProgressEvent(event)
  // Keep the library in step when an audiobook download finishes or fails.
  if ((event.kind ?? 'audio') !== 'audio') return
  if (event.status === 'done') {
    library.patchBooks([event.book_id], { liberation_status: 'liberated', last_format: event.format ?? null })
  } else if (event.status === 'error') {
    const book = library.books.find((b) => b.id === event.book_id)
    if (book && book.liberation_status !== 'liberated') library.patchBooks([event.book_id], { liberation_status: 'error' })
  }
})
settings.load()
downloads.load()

const activeCount = computed(() => downloads.activeJobs().length)
</script>
