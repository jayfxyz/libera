import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { BookSummary } from '@/api/client'
import { api } from '@/api/client'

export const useLibraryStore = defineStore('library', () => {
  const books = ref<BookSummary[]>([])
  const loading = ref(false)
  const searchQuery = ref('')
  const currentPage = ref(1)

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

  return { books, loading, searchQuery, currentPage, fetchBooks, updateBook, search }
})
