import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { BookSummary } from '@/api/client'
import { api } from '@/api/client'

export type StatusFilter = 'all' | 'liberated' | 'not_liberated' | 'in_progress'

export const useLibraryStore = defineStore('library', () => {
  const books = ref<BookSummary[]>([])
  const loading = ref(false)
  const searchQuery = ref('')
  const currentPage = ref(1)
  const statusFilter = ref<StatusFilter>('all')

  const filteredBooks = computed(() => {
    if (statusFilter.value === 'all') return books.value
    if (statusFilter.value === 'liberated') return books.value.filter((b) => b.liberation_status === 'liberated')
    if (statusFilter.value === 'not_liberated') return books.value.filter((b) => b.liberation_status === 'not_liberated')
    if (statusFilter.value === 'in_progress') return books.value.filter((b) => b.liberation_status === 'partial_download')
    return books.value
  })

  async function fetchBooks() {
    loading.value = true
    try {
      books.value = await api.library.list({
        q: searchQuery.value || undefined,
        page: currentPage.value,
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

  return { books, filteredBooks, loading, searchQuery, currentPage, statusFilter, fetchBooks, updateBook, search, setStatusFilter }
})
