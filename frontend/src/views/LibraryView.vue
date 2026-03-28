<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Library</h1>
      <input
        v-model="query"
        @input="onSearch"
        type="search"
        placeholder="Search books, authors, narrators..."
        class="w-80 px-4 py-2 bg-gray-800 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
      />
    </div>

    <div v-if="store.loading" class="text-gray-400">Loading...</div>

    <div v-else-if="store.books.length === 0" class="text-gray-400 mt-12 text-center">
      <p class="text-lg">No books yet.</p>
      <p class="text-sm mt-1">Add an Audible account and scan your library.</p>
    </div>

    <BookGrid v-else :books="store.books" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import BookGrid from '@/components/library/BookGrid.vue'
import { useLibraryStore } from '@/stores/library'

const store = useLibraryStore()
const query = ref('')

let searchTimer: ReturnType<typeof setTimeout>
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => store.search(query.value), 300)
}

onMounted(() => store.fetchBooks())
</script>
