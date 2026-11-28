<template>
  <div class="grid min-w-0 gap-6 md:grid-cols-2">
    <div class="flex min-w-0 flex-col gap-3">
      <h3 class="font-mono text-[11px] font-semibold tracking-wider text-ink-soft uppercase">Your layout</h3>
      <div class="rounded-[10px] border border-line bg-surface px-3.5 py-2.5">
        <span class="flex flex-wrap items-center gap-2">
          <span class="font-semibold">{{ current.name }}</span>
          <span v-if="current.recommended" class="rounded-full bg-ok-soft px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-ok-ink uppercase">Recommended</span>
        </span>
        <span class="block text-xs text-ink-soft">{{ current.why }}</span>
      </div>
      <!-- Pinned to the bottom of the column, level with the bottom of the preview beside it. -->
      <div class="mt-auto flex flex-wrap items-center gap-x-3 gap-y-2 pt-2">
        <button type="button" class="btn-secondary" @click="emit('change')">Change layout…</button>
        <span class="min-w-0 flex-1 basis-56 text-xs text-ink-soft">
          New downloads use the layout you pick. You can also move the books you already downloaded.
        </span>
      </div>
    </div>
    <LayoutPreview :layout="layout" title="Your library looks like" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NamingPreset } from '@/api/client'
import LayoutPreview from '@/components/shared/LayoutPreview.vue'
import { layoutById } from '@/lib/layouts'

/** The layout in use, with what it looks like. Changing it opens the layout dialog. */
const props = defineProps<{ layout: NamingPreset }>()
const emit = defineEmits<{ change: [] }>()

const current = computed(() => layoutById(props.layout))
</script>
