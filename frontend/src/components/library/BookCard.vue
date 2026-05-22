<template>
  <div
    class="group overflow-hidden rounded-lg border bg-card cursor-pointer transition-all hover:shadow-md"
    :class="book.is_deleted ? 'opacity-60' : ''"
    @click="emit('select', book)"
  >
    <!-- Cover -->
    <div class="aspect-square relative overflow-hidden bg-muted">
      <img
        v-if="book.cover_url"
        :src="book.cover_url"
        :alt="book.title"
        class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
      />
      <div v-else class="w-full h-full flex items-center justify-center text-muted-foreground text-4xl">📖</div>

      <!-- Status badge overlay -->
      <div v-if="book.liberation_status !== 'not_liberated' || book.is_deleted" class="absolute bottom-0 left-0 right-0 bg-linear-to-t from-black/60 to-transparent p-2">
        <span class="inline-flex items-center gap-1 text-xs font-medium px-1.5 py-0.5 rounded" :class="statusBadgeClass">
          {{ statusLabel }}
        </span>
      </div>

      <!-- In-progress progress bar -->
      <div v-if="book.liberation_status === 'partial_download'" class="absolute bottom-0 left-0 right-0 h-1 bg-muted">
        <div class="h-full bg-blue-500" style="width: 45%" />
      </div>
    </div>

    <!-- Info -->
    <div class="p-3 space-y-1">
      <h3 class="font-semibold line-clamp-2 leading-tight text-sm">{{ book.title }}</h3>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BookSummary } from '@/api/client'

const props = defineProps<{ book: BookSummary }>()
const emit = defineEmits<{ select: [book: BookSummary] }>()

const badgeMap: Record<string, { label: string; cls: string }> = {
  liberated: { label: '✓ Downloaded', cls: 'bg-green-600 text-white' },
  error: { label: '✗ Error', cls: 'bg-red-600 text-white' },
  partial_download: { label: '↓ Downloading', cls: 'bg-blue-600 text-white' },
}

const deletedBadge = { label: 'Removed', cls: 'bg-red-700 text-white' }

const statusBadgeClass = computed(() =>
  props.book.is_deleted ? deletedBadge.cls : (badgeMap[props.book.liberation_status]?.cls ?? ''),
)
const statusLabel = computed(() =>
  props.book.is_deleted ? deletedBadge.label : (badgeMap[props.book.liberation_status]?.label ?? ''),
)
</script>
