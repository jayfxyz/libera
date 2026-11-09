<template>
  <li class="flex items-center border-b border-line-faint last:border-b-0" :class="open ? 'bg-row-open' : checked ? 'bg-row-checked' : 'bg-surface'">
    <label class="flex h-[72px] w-12 shrink-0 cursor-pointer items-center justify-center md:w-[52px]">
      <input type="checkbox" class="checkbox" :checked="checked" :aria-label="`Select ${book.title}`" @change="emit('toggle')" />
    </label>
    <button
      type="button"
      class="flex min-w-0 flex-1 cursor-pointer items-center gap-3.5 py-2.5 pr-4 text-left"
      :aria-pressed="open"
      @click="emit('open')"
    >
      <BookCover :src="book.cover_url" :title="book.title" size="sm" rounded="rounded-lg" class="w-[52px] shrink-0" />
      <span class="flex min-w-0 flex-1 flex-col gap-0.5">
        <span class="text-[15px] font-semibold leading-[1.3] line-clamp-2">{{ book.title }}</span>
        <span class="truncate text-[13px] text-ink-soft">{{ byline(book) }}</span>
        <!-- Phones: status under the title instead of in its own column. -->
        <span class="mt-0.5 flex items-center gap-1.5 text-xs font-semibold sm:hidden" :class="status.text">
          <span class="size-2 rounded-full" :class="status.dot" />{{ status.label }}
        </span>
      </span>
      <span class="hidden lg:flex w-[150px] shrink flex-wrap gap-1">
        <span v-for="g in book.genres.slice(0, 2)" :key="g" class="chip max-w-full truncate" :title="g">{{ g }}</span>
      </span>
      <span class="hidden sm:flex w-[150px] shrink-0 flex-col gap-[5px]">
        <span class="flex items-center gap-1.5 text-xs font-semibold" :class="status.text">
          <span class="size-2 shrink-0 rounded-full" :class="status.dot" />{{ status.label }}
        </span>
        <span v-if="status.state === 'downloading'" class="h-1 overflow-hidden rounded-full bg-busy-track">
          <span class="block h-1 bg-busy transition-[width]" :style="{ width: `${status.percent}%` }" />
        </span>
      </span>
    </button>
  </li>
</template>

<script setup lang="ts">
import type { BookSummary } from '@/api/client'
import { byline, type BookStatus } from '@/lib/bookStatus'
import BookCover from './BookCover.vue'

defineProps<{ book: BookSummary; status: BookStatus; checked: boolean; open: boolean }>()
const emit = defineEmits<{ toggle: []; open: [] }>()
</script>
