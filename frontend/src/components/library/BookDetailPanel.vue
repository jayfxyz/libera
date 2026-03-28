<template>
  <!-- Backdrop -->
  <div class="fixed inset-0 bg-black/50 z-40" @click="emit('close')" />

  <!-- Slide-out panel -->
  <div class="fixed right-0 top-0 h-full w-full max-w-md bg-gray-900 z-50 flex flex-col shadow-2xl overflow-y-auto">
    <!-- Header -->
    <div class="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
      <h2 class="text-lg font-bold truncate pr-4">{{ book?.title ?? '…' }}</h2>
      <button @click="emit('close')" class="text-gray-400 hover:text-white shrink-0">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
        </svg>
      </button>
    </div>

    <div v-if="loading" class="flex-1 flex items-center justify-center text-gray-400">Loading…</div>
    <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400">{{ error }}</div>

    <template v-else-if="book">
      <!-- Cover + download -->
      <div class="px-5 py-5 flex gap-4 shrink-0">
        <div class="w-32 h-32 rounded-lg overflow-hidden bg-gray-800 shrink-0">
          <img v-if="book.cover_url" :src="book.cover_url" :alt="book.title" class="w-full h-full object-cover" />
          <div v-else class="w-full h-full flex items-center justify-center text-gray-600 text-4xl">📖</div>
        </div>
        <div class="min-w-0">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-xs px-2 py-0.5 rounded font-medium" :class="statusClass">{{ statusLabel }}</span>
          </div>
          <p v-if="book.authors.length" class="text-sm text-gray-300 mb-1">
            <span class="text-gray-500">By</span> {{ book.authors.join(', ') }}
          </p>
          <p v-if="book.narrators.length" class="text-sm text-gray-300 mb-1">
            <span class="text-gray-500">Narrated by</span> {{ book.narrators.join(', ') }}
          </p>
          <p v-if="book.series.length" class="text-sm text-gray-300 mb-2">
            <span class="text-gray-500">Series:</span>
            <span v-for="(s, i) in book.series" :key="i">
              {{ s.name }}<span v-if="s.index"> #{{ s.index }}</span><span v-if="i < book.series.length - 1">, </span>
            </span>
          </p>
          <p v-if="book.length_minutes" class="text-xs text-gray-500">{{ formatDuration(book.length_minutes) }}</p>
        </div>
      </div>

      <!-- Download button -->
      <div class="px-5 pb-4 shrink-0">
        <button
          @click="handleDownload"
          :disabled="isDownloading"
          class="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm font-medium flex items-center justify-center gap-2"
        >
          <svg v-if="isDownloading" class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          {{ isDownloading ? 'Downloading…' : book.liberation_status === 'liberated' ? 'Re-download' : 'Download' }}
        </button>

        <!-- Active download progress -->
        <div v-if="activeJob" class="mt-3">
          <div class="flex justify-between text-xs text-gray-400 mb-1">
            <span>{{ activeJob.status === 'decrypting' ? 'Decrypting…' : 'Downloading…' }}</span>
            <span>{{ activeJob.percent }}%</span>
          </div>
          <div class="w-full bg-gray-700 rounded-full h-1.5">
            <div class="h-1.5 rounded-full bg-indigo-500 transition-all" :style="{ width: `${activeJob.percent}%` }" />
          </div>
        </div>
      </div>

      <div class="border-t border-gray-800 mx-5 shrink-0" />

      <!-- Metadata -->
      <div class="px-5 py-4 space-y-4">
        <!-- Description -->
        <div v-if="book.description">
          <h3 class="text-xs text-gray-500 uppercase tracking-wider mb-2">Description</h3>
          <p class="text-sm text-gray-300 leading-relaxed line-clamp-6">{{ book.description }}</p>
        </div>

        <!-- Details grid -->
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div v-if="book.publisher">
            <span class="text-gray-500 text-xs uppercase tracking-wider block mb-0.5">Publisher</span>
            <span class="text-gray-300">{{ book.publisher }}</span>
          </div>
          <div v-if="book.language">
            <span class="text-gray-500 text-xs uppercase tracking-wider block mb-0.5">Language</span>
            <span class="text-gray-300">{{ book.language }}</span>
          </div>
          <div v-if="book.audible_rating">
            <span class="text-gray-500 text-xs uppercase tracking-wider block mb-0.5">Audible Rating</span>
            <span class="text-gray-300">★ {{ book.audible_rating.toFixed(1) }}</span>
          </div>
        </div>

        <!-- Tags -->
        <div v-if="tagList.length">
          <h3 class="text-xs text-gray-500 uppercase tracking-wider mb-2">Tags</h3>
          <div class="flex gap-1.5 flex-wrap">
            <span
              v-for="tag in tagList"
              :key="tag"
              class="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded"
            >{{ tag }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { BookDetail } from '@/api/client'
import { api } from '@/api/client'
import { useDownloadsStore } from '@/stores/downloads'

const props = defineProps<{ bookId: number }>()
const emit = defineEmits<{ close: [] }>()

const book = ref<BookDetail | null>(null)
const loading = ref(true)
const error = ref('')

const downloadsStore = useDownloadsStore()

onMounted(async () => {
  try {
    book.value = await api.library.get(props.bookId)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const activeJob = computed(() =>
  book.value
    ? Array.from(downloadsStore.jobs.values()).find(
        (j) => j.book_id === book.value!.id && j.status !== 'done' && j.status !== 'error',
      )
    : undefined,
)

const isDownloading = computed(() => !!activeJob.value)

async function handleDownload() {
  if (!book.value) return
  await downloadsStore.enqueue(book.value.id, book.value.audible_id, book.value.account_id)
}

const statusMap: Record<string, { label: string; cls: string }> = {
  liberated: { label: 'Downloaded', cls: 'bg-green-700 text-green-100' },
  error: { label: 'Error', cls: 'bg-red-700 text-red-100' },
  partial_download: { label: 'Partial', cls: 'bg-yellow-700 text-yellow-100' },
  not_liberated: { label: 'Not Downloaded', cls: 'bg-gray-700 text-gray-300' },
}
const statusClass = computed(() => statusMap[book.value?.liberation_status ?? 'not_liberated']?.cls ?? '')
const statusLabel = computed(() => statusMap[book.value?.liberation_status ?? 'not_liberated']?.label ?? '')

const tagList = computed(() =>
  book.value?.tags ? book.value.tags.split(' ').filter(Boolean) : [],
)

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}
</script>
