<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold">Library</h1>
      <div class="flex items-center gap-3">
        <button
          @click="rescan"
          :disabled="rescanning"
          class="px-3 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-sm text-gray-300"
          :title="rescanMessage || 'Match books to files already in the output directory'"
        >
          {{ rescanning ? 'Scanning…' : rescanMessage || 'Scan Files' }}
        </button>
        <input
        v-model="query"
        @input="onSearch"
        type="search"
        placeholder="Search books, authors, narrators..."
        class="w-80 px-4 py-2 bg-gray-800 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
    </div>

    <!-- Filter pills -->
    <div class="flex gap-2 mb-6">
      <button
        v-for="pill in pills"
        :key="pill.value"
        @click="store.setStatusFilter(pill.value)"
        class="px-3 py-1 rounded-full text-sm font-medium transition-colors"
        :class="store.statusFilter === pill.value
          ? 'bg-indigo-600 text-white'
          : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'"
      >
        {{ pill.label }}
        <span v-if="pill.count > 0 || store.statusFilter === pill.value" class="ml-1 opacity-70 text-xs">
          {{ pill.count }}
        </span>
      </button>
    </div>

    <div v-if="store.loading" class="text-gray-400">Loading...</div>

    <div v-else-if="store.filteredBooks.length === 0" class="text-gray-400 mt-12 text-center">
      <p v-if="store.books.length === 0" class="text-lg">No books yet.</p>
      <p v-if="store.books.length === 0" class="text-sm mt-1">Add an Audible account and scan your library.</p>
      <p v-else class="text-lg">No books match this filter.</p>
    </div>

    <BookGrid v-else :books="store.filteredBooks" @select="onBookSelect" />

    <!-- Book detail slide-out -->
    <BookDetailPanel v-if="selectedBook" :book-id="selectedBook.id" @close="selectedBook = null" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import BookGrid from '@/components/library/BookGrid.vue'
import BookDetailPanel from '@/components/library/BookDetailPanel.vue'
import { useLibraryStore } from '@/stores/library'
import type { StatusFilter } from '@/stores/library'
import type { BookSummary } from '@/api/client'
import { api } from '@/api/client'

const store = useLibraryStore()
const query = ref('')
const selectedBook = ref<BookSummary | null>(null)
const rescanning = ref(false)
const rescanMessage = ref('')

async function rescan() {
  rescanning.value = true
  rescanMessage.value = ''
  try {
    const { matched } = await api.library.rescan()
    rescanMessage.value = matched > 0 ? `${matched} matched` : 'No matches'
    if (matched > 0) store.fetchBooks()
    setTimeout(() => { rescanMessage.value = '' }, 3000)
  } finally {
    rescanning.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout>
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => store.search(query.value), 300)
}

function onBookSelect(book: BookSummary) {
  selectedBook.value = book
}

type Pill = { label: string; value: StatusFilter; count: number }

const removedCount = computed(() => store.books.filter((b) => b.is_deleted).length)

const pills = computed<Pill[]>(() => {
  const base: Pill[] = [
    { label: 'All', value: 'all', count: store.books.filter((b) => !b.is_deleted).length },
    { label: 'Downloaded', value: 'liberated', count: store.books.filter((b) => !b.is_deleted && b.liberation_status === 'liberated').length },
    { label: 'Not Downloaded', value: 'not_liberated', count: store.books.filter((b) => !b.is_deleted && b.liberation_status === 'not_liberated').length },
    { label: 'In Progress', value: 'in_progress', count: store.books.filter((b) => !b.is_deleted && b.liberation_status === 'partial_download').length },
  ]
  if (removedCount.value > 0 || store.statusFilter === 'removed') {
    base.push({ label: 'Removed', value: 'removed', count: removedCount.value })
  }
  return base
})

onMounted(() => store.fetchBooks())
</script>
