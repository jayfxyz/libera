<template>
  <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
    <BookCard v-for="book in books" :key="book.id" :book="book" @select="emit('select', $event)" />
  </div>
</template>

<script setup lang="ts">
import BookCard from './BookCard.vue'
import type { BookSummary } from '@/api/client'

defineProps<{ books: BookSummary[] }>()
const emit = defineEmits<{ select: [book: BookSummary] }>()
</script>
