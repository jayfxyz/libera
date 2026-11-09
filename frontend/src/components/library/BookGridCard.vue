<template>
  <div class="relative flex min-w-0 flex-col">
    <button type="button" class="flex min-w-0 cursor-pointer flex-col gap-2 text-left" :aria-pressed="open" @click="emit('open')">
      <span
        class="block rounded-[10px]"
        :class="open ? 'shadow-[0_0_0_3px_#F5F5F2,0_0_0_5px_#121418]' : ''"
      >
        <BookCover :src="book.cover_url" :title="book.title" :author="book.authors[0]" />
      </span>
      <span class="text-sm font-semibold leading-[1.3] line-clamp-2">{{ book.title }}</span>
      <span class="flex items-center gap-1.5 text-xs font-medium" :class="status.text">
        <span class="size-2 shrink-0 rounded-full" :class="status.dot" />{{ status.label }}
      </span>
      <span v-if="status.state === 'downloading'" class="-mt-1 h-1 overflow-hidden rounded-full bg-busy-track">
        <span class="block h-1 bg-busy transition-[width]" :style="{ width: `${status.percent}%` }" />
      </span>
    </button>
    <label
      class="absolute left-1.5 top-1.5 flex size-9 cursor-pointer items-center justify-center rounded-lg bg-white/95 shadow-[0_1px_2px_rgba(0,0,0,0.18)]"
    >
      <input type="checkbox" class="checkbox" :checked="checked" :aria-label="`Select ${book.title}`" @change="emit('toggle')" />
    </label>
  </div>
</template>

<script setup lang="ts">
import type { BookSummary } from '@/api/client'
import type { BookStatus } from '@/lib/bookStatus'
import BookCover from './BookCover.vue'

defineProps<{ book: BookSummary; status: BookStatus; checked: boolean; open: boolean }>()
const emit = defineEmits<{ toggle: []; open: [] }>()
</script>
