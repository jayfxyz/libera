<template>
  <li class="group flex items-center border-b border-line-faint last:border-b-0" :class="open ? 'bg-row-open' : checked ? 'bg-row-checked' : 'bg-surface'">
    <!-- Not selecting: shown on hover or keyboard focus; touch screens use the Select button. -->
    <label
      class="flex h-[72px] w-12 shrink-0 cursor-pointer items-center justify-center md:w-[52px]"
      :class="selecting ? '' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100 pointer-coarse:hidden'"
    >
      <input type="checkbox" class="checkbox" :checked="checked" :aria-label="`Select ${book.title}`" @change="emit('toggle')" />
    </label>
    <button
      type="button"
      class="flex min-w-0 flex-1 cursor-pointer items-center gap-3.5 py-2.5 pr-4 @md:pr-3.5 text-left"
      :class="selecting ? '' : 'pointer-coarse:pl-4'"
      :aria-pressed="open"
      @click="emit('open')"
    >
      <BookCover :src="book.cover_url" :title="book.title" size="sm" rounded="rounded-lg" class="w-[52px] shrink-0" />
      <span class="flex min-w-0 flex-1 flex-col gap-0.5">
        <span class="text-[15px] font-semibold leading-[1.3] line-clamp-2">{{ book.title }}</span>
        <span class="truncate text-[13px] text-ink-soft">{{ byline(book) }}</span>
        <!-- Narrow lists: status and date under the title instead of in their own columns. -->
        <span class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs @xl:hidden">
          <span class="flex items-center gap-1.5 font-semibold @md:hidden" :class="status.text">
            <LockIcon v-if="status.state === 'unavailable'" class="size-3 shrink-0" aria-hidden="true" />
            <span v-else class="size-2 rounded-full" :class="status.dot" />{{ status.label }}
          </span>
          <span v-if="added" class="text-ink-soft">Added {{ added }}</span>
        </span>
      </span>
      <!-- Columns appear as the list gets wider (it narrows when the book panel is open). -->
      <span class="hidden @4xl:flex w-[150px] shrink flex-wrap gap-1">
        <span v-for="g in book.genres.slice(0, 2)" :key="g" class="chip max-w-full truncate" :title="g">{{ g }}</span>
      </span>
      <span v-if="account" class="hidden @3xl:block w-[150px] shrink-0 truncate text-[13px] text-ink-soft" :title="account">{{ account }}</span>
      <span class="hidden @xl:block w-[100px] shrink-0 text-[13px] text-ink-soft" :title="added ? `Added to your Audible library on ${added}` : undefined">{{ added || '—' }}</span>
    </button>
    <div class="hidden @md:flex w-[166px] shrink-0 flex-col gap-[5px] pr-4">
      <UnavailablePopover v-if="status.state === 'unavailable'" align="end" />
      <button v-else type="button" class="flex cursor-pointer flex-col gap-[5px] text-left" @click="emit('open')">
        <span class="flex items-center gap-1.5 text-xs font-semibold" :class="status.text">
          <span class="size-2 shrink-0 rounded-full" :class="status.dot" />{{ status.label }}
        </span>
        <span v-if="status.state === 'downloading'" class="h-1 overflow-hidden rounded-full bg-busy-track">
          <span class="block h-1 bg-busy transition-[width]" :style="{ width: `${status.percent}%` }" />
        </span>
      </button>
    </div>
  </li>
</template>

<script setup lang="ts">
import type { BookSummary } from '@/api/client'
import { computed } from 'vue'
import { LockIcon } from '@lucide/vue'
import { byline, formatDate, type BookStatus } from '@/lib/bookStatus'
import BookCover from './BookCover.vue'
import UnavailablePopover from './UnavailablePopover.vue'

const props = defineProps<{
  book: BookSummary
  status: BookStatus
  checked: boolean
  open: boolean
  selecting: boolean
  /** The book's account (e.g. "🇬🇧 Personal"); omitted when there's only one account. */
  account?: string
}>()
const added = computed(() => formatDate(props.book.date_added))
const emit = defineEmits<{ toggle: []; open: [] }>()
</script>
