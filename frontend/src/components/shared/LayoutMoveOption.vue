<template>
  <div class="flex flex-col gap-3">
    <label class="flex items-start gap-2.5 text-sm">
      <input v-model="enabled" type="checkbox" class="mt-0.5 size-4 accent-brand" :disabled="disabled" />
      <span>
        <span class="font-semibold">Update previously downloaded books to this layout?</span>
        <span class="block text-xs text-ink-soft">
          {{ enabled ? 'Libera will move each book folder and remember the new location when you save.' : 'Off: only new downloads use the layout, and your existing files stay where they are.' }}
        </span>
      </span>
    </label>
    <div v-if="enabled" class="pl-6.5">
      <LayoutMovePreview :preview="preview" :loading="loading" :error="error" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { MovePreview } from '@/api/client'
import LayoutMovePreview from '@/components/shared/LayoutMovePreview.vue'

/** The checkbox and, once it is on, what moving would do. The parent decides when the move runs (on save). */
const enabled = defineModel<boolean>({ required: true })

defineProps<{ preview: MovePreview | null; loading: boolean; error: string; disabled?: boolean }>()
</script>
