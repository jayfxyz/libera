<template>
  <div class="group relative cursor-pointer" :class="book.is_deleted ? 'opacity-50' : ''" @click="emit('select', book)">
    <div class="aspect-square bg-gray-800 rounded-lg overflow-hidden">
      <img
        v-if="book.cover_url"
        :src="book.cover_url"
        :alt="book.title"
        class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
      />
      <div v-else class="w-full h-full flex items-center justify-center text-gray-600 text-4xl">📖</div>
    </div>

    <!-- Removed from Audible overlay -->
    <div v-if="book.is_deleted" class="absolute inset-0 flex items-end justify-center pb-2 pointer-events-none">
      <span class="text-xs bg-black/70 text-gray-300 px-2 py-0.5 rounded">Removed from Audible</span>
    </div>

    <!-- Status badge -->
    <span
      v-if="book.liberation_status !== 'not_liberated'"
      class="absolute top-2 right-2 text-xs px-1.5 py-0.5 rounded"
      :class="statusBadgeClass"
    >{{ statusLabel }}</span>

    <!-- Download button (visible on hover) -->
    <button
      class="absolute bottom-12 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-2 py-1 rounded flex items-center gap-1"
      :disabled="isDownloading"
      @click.stop="handleDownload"
    >
      <svg v-if="isDownloading" class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
      <span>{{ isDownloading ? 'Downloading…' : 'Download' }}</span>
    </button>

    <div class="mt-2">
      <p class="text-sm font-medium leading-tight line-clamp-2">{{ book.title }}</p>
      <div class="flex gap-1 mt-1 flex-wrap">
        <span
          v-for="tag in tagList"
          :key="tag"
          class="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded"
        >{{ tag }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BookSummary } from '@/api/client'
import { useDownloadsStore } from '@/stores/downloads'

const props = defineProps<{ book: BookSummary }>()
const emit = defineEmits<{ select: [book: BookSummary] }>()

const downloadsStore = useDownloadsStore()

const tagList = computed(() => (props.book.tags ? props.book.tags.split(' ').filter(Boolean) : []))

const isDownloading = computed(() =>
  Array.from(downloadsStore.jobs.values()).some(
    (j) => j.book_id === props.book.id && j.status !== 'done' && j.status !== 'error',
  ),
)

async function handleDownload() {
  await downloadsStore.enqueue(props.book.id, props.book.audible_id, props.book.account_id)
}

const badgeClasses: Record<string, string> = {
  liberated: 'bg-green-700 text-green-100',
  error: 'bg-red-700 text-red-100',
  partial_download: 'bg-yellow-700 text-yellow-100',
}
const badgeLabels: Record<string, string> = {
  liberated: '✓',
  error: '✗',
  partial_download: '~',
}
const statusBadgeClass = computed(() => badgeClasses[props.book.liberation_status] ?? '')
const statusLabel = computed(() => badgeLabels[props.book.liberation_status] ?? '')
</script>
