import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { BookSummary, LibrarySort, SortOrder } from '@/api/client'
import { api } from '@/api/client'

/** Sort options, each with the direction it starts in when picked. */
export const sortOptions: { value: LibrarySort; label: string; defaultOrder: SortOrder }[] = [
  { value: 'title', label: 'Title', defaultOrder: 'asc' },
  { value: 'author', label: 'Author', defaultOrder: 'asc' },
  { value: 'added', label: 'Date added', defaultOrder: 'desc' },
  { value: 'released', label: 'Release date', defaultOrder: 'desc' },
  { value: 'length', label: 'Length', defaultOrder: 'desc' },
  { value: 'series', label: 'Series', defaultOrder: 'asc' },
  { value: 'rating', label: 'Audible rating', defaultOrder: 'desc' },
  { value: 'downloaded', label: 'Recently downloaded', defaultOrder: 'desc' },
]

const SORT_KEY = 'library.sort'

// The chosen sort is remembered per browser; storage may be unavailable.
function loadSort(): { sort: LibrarySort; order: SortOrder } {
  try {
    const saved = JSON.parse(localStorage.getItem(SORT_KEY) ?? 'null')
    const opt = sortOptions.find((o) => o.value === saved?.sort)
    if (opt && (saved.order === 'asc' || saved.order === 'desc')) return { sort: opt.value, order: saved.order }
  } catch {
    /* ignore */
  }
  return { sort: 'title', order: 'asc' }
}

function saveSort(sort: LibrarySort, order: SortOrder) {
  try {
    localStorage.setItem(SORT_KEY, JSON.stringify({ sort, order }))
  } catch {
    /* ignore */
  }
}

export type StatusFilter = 'all' | 'liberated' | 'not_liberated' | 'in_progress' | 'removed'

export const useLibraryStore = defineStore('library', () => {
  const books = ref<BookSummary[]>([])
  const loading = ref(false)
  const searchQuery = ref('')
  const currentPage = ref(1)
  const statusFilter = ref<StatusFilter>('all')
  const initialSort = loadSort()
  const sort = ref<LibrarySort>(initialSort.sort)
  const order = ref<SortOrder>(initialSort.order)

  const filteredBooks = computed(() => {
    if (statusFilter.value === 'all') return books.value.filter((b) => !b.is_deleted)
    if (statusFilter.value === 'liberated') return books.value.filter((b) => !b.is_deleted && b.liberation_status === 'liberated')
    if (statusFilter.value === 'not_liberated') return books.value.filter((b) => !b.is_deleted && b.liberation_status === 'not_liberated')
    if (statusFilter.value === 'in_progress') return books.value.filter((b) => !b.is_deleted && b.liberation_status === 'partial_download')
    if (statusFilter.value === 'removed') return books.value.filter((b) => b.is_deleted)
    return books.value
  })

  async function fetchBooks() {
    loading.value = true
    try {
      books.value = await api.library.list({
        q: searchQuery.value || undefined,
        page: currentPage.value,
        sort: sort.value,
        order: order.value,
      })
    } finally {
      loading.value = false
    }
  }

  async function updateBook(id: number, patch: Partial<{ tags: string; user_rating: number; is_finished: boolean }>) {
    await api.library.update(id, patch)
    const book = books.value.find((b) => b.id === id)
    if (book) {
      if (patch.tags !== undefined) book.tags = patch.tags
      if (patch.is_finished !== undefined) book.is_finished = patch.is_finished
    }
  }

  function search(q: string) {
    searchQuery.value = q
    currentPage.value = 1
    fetchBooks()
  }

  function setStatusFilter(f: StatusFilter) {
    statusFilter.value = f
  }

  /** Picking a new sort starts in its natural direction. */
  function setSort(s: LibrarySort) {
    if (s === sort.value) return
    sort.value = s
    order.value = sortOptions.find((o) => o.value === s)?.defaultOrder ?? 'asc'
    applySort()
  }

  function toggleOrder() {
    order.value = order.value === 'asc' ? 'desc' : 'asc'
    applySort()
  }

  function applySort() {
    saveSort(sort.value, order.value)
    currentPage.value = 1
    fetchBooks()
  }

  return {
    books, filteredBooks, loading, searchQuery, currentPage, statusFilter, sort, order,
    fetchBooks, updateBook, search, setStatusFilter, setSort, toggleOrder,
  }
})
