<template>
  <!-- Desktop: rail | page. Phones: top bar with a hamburger menu, page below. -->
  <div class="flex h-dvh flex-col overflow-hidden bg-paper text-ink md:flex-row">
    <AppRail :active-downloads="activeCount" />
    <MobileNav :active-downloads="activeCount" />
    <main class="flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <RouterView />
    </main>
    <LayoutDialog />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppRail from '@/components/shared/AppRail.vue'
import LayoutDialog from '@/components/shared/LayoutDialog.vue'
import MobileNav from '@/components/shared/MobileNav.vue'
import { useDownloadsStore } from '@/stores/downloads'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import { useEventStream } from '@/composables/useEventStream'

const downloads = useDownloadsStore()
const library = useLibraryStore()
const settings = useSettingsStore()

const stream = useEventStream()
stream.on('download.updated', (download) => downloads.upsert(download))
stream.on('book.updated', (book) => library.upsertBook(book))
// The stream has no replay: whatever happened while it was down comes from fresh snapshots.
stream.onOpen(() => {
  downloads.load()
  if (library.books.length) library.fetchBooks()
})
settings.load()

const activeCount = computed(() => downloads.active().length)
</script>
