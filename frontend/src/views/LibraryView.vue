<template>
  <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
    <!-- Header -->
    <div class="border-b p-4 md:p-6 shrink-0">
      <div class="flex items-center justify-between gap-3 mb-3 md:mb-4">
        <div>
          <h2 class="text-2xl font-semibold">Library</h2>
          <p class="text-sm text-muted-foreground">
            {{ store.filteredBooks.length }} {{ store.filteredBooks.length === 1 ? 'book' : 'books' }}
          </p>
        </div>
        <div class="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" as-child>
            <a href="/api/library/export?format=csv" download="library.csv" aria-label="Export CSV" title="Export CSV">
              <svg xmlns="http://www.w3.org/2000/svg" class="sm:mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
              </svg>
              <span class="sm:hidden ml-1">CSV</span><span class="hidden sm:inline">Export CSV</span>
            </a>
          </Button>
          <Button variant="outline" size="sm" as-child>
            <a href="/api/library/export?format=json" download="library.json" aria-label="Export JSON" title="Export JSON">
              <svg xmlns="http://www.w3.org/2000/svg" class="sm:mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
              </svg>
              <span class="sm:hidden ml-1">JSON</span><span class="hidden sm:inline">Export JSON</span>
            </a>
          </Button>
          <Button variant="outline" size="sm" :disabled="rescanning" aria-label="Scan files" title="Scan files" @click="rescan">
            <svg xmlns="http://www.w3.org/2000/svg" class="sm:mr-2 h-4 w-4" :class="rescanning ? 'animate-spin' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            <span class="hidden sm:inline">{{ rescanning ? 'Scanning…' : rescanMessage || 'Scan Files' }}</span>
          </Button>
        </div>
      </div>

      <!-- Search -->
      <div class="relative mb-3 md:mb-4">
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

      <!-- Filter pills + sort -->
      <div class="flex items-center justify-between gap-3 md:gap-4 flex-wrap">
      <div class="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4 md:mx-0 md:px-0 md:flex-wrap w-[calc(100%+2rem)] md:w-auto">
        <Badge
          v-for="pill in pills"
          :key="pill.value"
          :variant="store.statusFilter === pill.value ? 'default' : 'outline'"
          class="cursor-pointer shrink-0 py-1"
          @click="store.setStatusFilter(pill.value)"
        >
          {{ pill.label }}
          <span class="ml-1 opacity-60 text-xs">({{ pill.count }})</span>
        </Badge>
      </div>

      <div class="flex items-center gap-2 w-full sm:w-auto">
        <span class="text-sm text-muted-foreground shrink-0">Sort by</span>
        <Select :model-value="store.sort" @update:model-value="(v) => store.setSort(v as LibrarySort)">
          <SelectTrigger class="flex-1 sm:flex-none sm:w-48 h-8" aria-label="Sort by">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in sortOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          class="h-8 w-8 p-0 shrink-0"
          :aria-label="store.order === 'asc' ? 'Ascending, click for descending' : 'Descending, click for ascending'"
          :title="orderHint"
          @click="store.toggleOrder()"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 transition-transform" :class="store.order === 'desc' ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
          </svg>
        </Button>
      </div>
      </div>
    </div>

    <!-- Book Grid -->
    <div class="flex-1 overflow-y-auto">
      <!-- @container: columns follow the space the grid has (smaller when the
           download panel is open), not the window width. -->
      <div class="@container p-4 md:p-6">
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
        <div v-else class="grid grid-cols-2 @md:grid-cols-3 @xl:grid-cols-4 @2xl:grid-cols-5 @4xl:grid-cols-6 gap-3 md:gap-4">
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useLibraryStore, sortOptions } from '@/stores/library'
import type { StatusFilter } from '@/stores/library'
import type { BookSummary, LibrarySort } from '@/api/client'
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

// Plain-words description of the current direction, for the toggle's tooltip.
const orderHint = computed(() => {
  const asc = store.order === 'asc'
  switch (store.sort) {
    case 'title':
    case 'author':
    case 'series':
      return asc ? 'A → Z' : 'Z → A'
    case 'length':
      return asc ? 'Shortest first' : 'Longest first'
    case 'rating':
      return asc ? 'Lowest first' : 'Highest first'
    default:
      return asc ? 'Oldest first' : 'Newest first'
  }
})

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
