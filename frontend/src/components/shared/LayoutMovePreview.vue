<template>
  <div class="flex flex-col gap-3 text-sm" aria-live="polite">
    <p v-if="loading" class="text-ink-soft">Checking your library…</p>
    <p v-else-if="error" class="text-destructive" role="alert">{{ error }}</p>
    <template v-else-if="preview">
      <div class="flex flex-wrap gap-2">
        <span class="rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-medium text-ok-ink">
          {{ bookCount(preview.to_move) }} will move
        </span>
        <span v-if="preview.in_place" class="rounded-full bg-chip-soft px-2.5 py-0.5 text-xs text-ink-soft">
          {{ bookCount(preview.in_place) }} already there
        </span>
        <span v-if="preview.skipped_total" class="rounded-full bg-warn-soft px-2.5 py-0.5 text-xs font-medium text-warn-ink">
          {{ bookCount(preview.skipped_total) }} can't be moved safely
        </span>
      </div>
      <p class="text-xs text-ink-soft">
        Each book's whole folder moves, so its cover, PDF and chapter files go with it. Nothing is overwritten.
      </p>

      <p v-if="preview.to_rename" class="text-xs text-ink-soft">
        {{ bookCount(preview.to_rename) }} from older versions also {{ preview.to_rename === 1 ? 'gets its' : 'get their' }} files
        renamed to include the book's ID, like a new download.
      </p>

      <div v-if="preview.examples.length" class="min-w-0 overflow-hidden rounded-[10px] border border-line">
        <div v-for="example in preview.examples" :key="example.from" class="grid gap-1 border-b border-line-faint px-3 py-2 font-mono text-xs last:border-b-0 sm:grid-cols-[1fr_auto_1fr] sm:gap-2">
          <span class="min-w-0 break-words text-ink-soft">{{ example.from }}</span>
          <ArrowRightIcon class="hidden size-3.5 self-center text-brand sm:block" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ example.to }}</span>
        </div>
        <p v-if="preview.to_move > preview.examples.length" class="bg-paper px-3 py-1.5 text-xs text-ink-soft">
          and {{ preview.to_move - preview.examples.length }} more
        </p>
      </div>

      <details v-if="preview.skipped_total" class="group">
        <summary class="flex cursor-pointer list-none items-center gap-1.5 text-xs font-semibold text-ink-soft hover:text-ink">
          <ChevronRightIcon class="size-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />Which books stay where they are
        </summary>
        <ul class="mt-2 flex flex-col gap-1 text-xs">
          <li v-for="book in preview.skipped" :key="book.book_id" class="flex flex-wrap gap-x-2">
            <span class="font-medium">{{ book.title || 'Untitled' }}</span>
            <span class="text-ink-soft">{{ book.reason }}</span>
          </li>
          <li v-if="preview.skipped_total > preview.skipped.length" class="text-ink-soft">
            and {{ preview.skipped_total - preview.skipped.length }} more
          </li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ArrowRightIcon, ChevronRightIcon } from '@lucide/vue'
import type { MovePreview } from '@/api/client'
import { bookCount } from '@/lib/layouts'

defineProps<{ preview: MovePreview | null; loading: boolean; error: string }>()
</script>
