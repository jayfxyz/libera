<template>
  <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
    <!-- Header -->
    <div class="border-b p-6 shrink-0">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-2xl font-semibold">Library</h2>
          <p class="text-sm text-muted-foreground">
            {{ store.filteredBooks.length }} {{ store.filteredBooks.length === 1 ? 'book' : 'books' }}
          </p>
        </div>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" as-child>
            <a href="/api/library/export?format=csv" download="library.csv">
              <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
              </svg>
              Export CSV
            </a>
          </Button>
          <Button variant="outline" size="sm" as-child>
            <a href="/api/library/export?format=json" download="library.json">
              <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
              </svg>
              Export JSON
            </a>
          </Button>
          <Button variant="outline" size="sm" :disabled="rescanning" @click="rescan">
            <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" :class="rescanning ? 'animate-spin' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            {{ rescanning ? 'Scanning…' : rescanMessage || 'Scan Files' }}
          </Button>
        </div>
      </div>

      <!-- Search -->
      <div class="relative mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <Input
          v-model="query"
          type="search"
          placeholder="Search by title, author, narrator, or tags..."
          class="pl-9"
          @input="onSearch"
        />
      </div>

      <!-- Filter pills -->
      <div class="flex gap-2 flex-wrap">
        <Badge
          v-for="pill in pills"
          :key="pill.value"
          :variant="store.statusFilter === pill.value ? 'default' : 'outline'"
          class="cursor-pointer"
          @click="store.setStatusFilter(pill.value)"
        >
          {{ pill.label }}
          <span class="ml-1 opacity-60 text-xs">({{ pill.count }})</span>
        </Badge>
      </div>
    </div>

    <!-- Book Grid -->
    <div class="flex-1 overflow-y-auto">
      <div class="p-6">
        <div v-if="store.loading" class="flex items-center justify-center py-12 text-muted-foreground">
          Loading…
        </div>
        <div v-else-if="store.filteredBooks.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-muted-foreground mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
          </svg>
          <h3 class="font-semibold mb-2">
            {{ store.books.length === 0 ? 'No books yet' : 'No books match this filter' }}
          </h3>
          <p class="text-sm text-muted-foreground">
            {{ store.books.length === 0 ? 'Add an Audible account and scan your library.' : 'Try adjusting your search or filters.' }}
          </p>
        </div>
        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          <BookCard
            v-for="book in store.filteredBooks"
            :key="book.id"
            :book="book"
            @select="onBookSelect"
          />
        </div>
      </div>
    </div>
    <!-- Book Detail Panel (fixed overlay) -->
    <BookDetailPanel v-if="selectedBook" :book-id="selectedBook.id" @close="selectedBook = null" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import BookCard from '@/components/library/BookCard.vue'
import BookDetailPanel from '@/components/library/BookDetailPanel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
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

const removedCount = computed(() => store.books.filter(b => b.is_deleted).length)

const pills = computed<Pill[]>(() => {
  const base: Pill[] = [
    { label: 'All', value: 'all', count: store.books.filter(b => !b.is_deleted).length },
    { label: 'Downloaded', value: 'liberated', count: store.books.filter(b => !b.is_deleted && b.liberation_status === 'liberated').length },
    { label: 'Not Downloaded', value: 'not_liberated', count: store.books.filter(b => !b.is_deleted && b.liberation_status === 'not_liberated').length },
    { label: 'In Progress', value: 'in_progress', count: store.books.filter(b => !b.is_deleted && b.liberation_status === 'partial_download').length },
  ]
  if (removedCount.value > 0 || store.statusFilter === 'removed') {
    base.push({ label: 'Removed', value: 'removed', count: removedCount.value })
  }
  return base
})

onMounted(() => store.fetchBooks())
</script>
