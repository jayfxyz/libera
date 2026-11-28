<template>
  <div class="flex flex-col gap-4 text-sm" role="status">
    <div class="flex flex-col gap-1">
      <p class="flex items-center gap-2 text-base font-semibold">
        <CircleCheckIcon class="size-5 shrink-0 text-ok" aria-hidden="true" />{{ headline }}
      </p>
      <p v-if="result.to_rename" class="pl-7 text-ink-soft">
        {{ bookCount(result.to_rename) }} also had {{ result.to_rename === 1 ? 'its' : 'their' }} files renamed to include the book's ID.
      </p>
      <p class="pl-7 text-ink-soft">New downloads use {{ layoutName }} too.</p>
    </div>
    <div v-if="result.skipped_total" class="flex flex-col gap-2 rounded-[10px] border border-line bg-paper p-4">
      <p class="font-semibold">Left where {{ result.skipped_total === 1 ? 'it is' : 'they are' }} ({{ result.skipped_total }})</p>
      <ul class="flex flex-col gap-1 text-xs">
        <li v-for="book in result.skipped" :key="book.book_id" class="flex flex-wrap gap-x-2">
          <span class="font-medium">{{ book.title || 'Untitled' }}</span>
          <span class="text-ink-soft">{{ book.reason }}</span>
        </li>
        <li v-if="result.skipped_total > result.skipped.length" class="text-ink-soft">
          and {{ result.skipped_total - result.skipped.length }} more
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckIcon } from '@lucide/vue'
import type { MoveResult } from '@/api/client'
import { bookCount } from '@/lib/layouts'

/** What a move did: how many books moved and renamed, and which were left where they are, with the reason. */
const props = defineProps<{ result: MoveResult; layoutName: string }>()

const headline = computed(() =>
  props.result.moved === 0 ? 'No books needed moving.' : `Moved ${bookCount(props.result.moved)} to ${props.layoutName}.`,
)
</script>
