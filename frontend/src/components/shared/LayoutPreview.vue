<template>
  <div class="flex min-w-0 flex-col gap-2">
    <h3 class="font-mono text-[11px] font-semibold tracking-wider text-ink-soft uppercase">{{ title }}</h3>
    <div class="min-w-0 rounded-[10px] border border-line bg-paper p-4">
      <div class="mb-2 flex justify-between gap-2 font-mono text-[10px] text-ink-soft">
        <span>/audiobooks</span><span>example books</span>
      </div>
      <FileTree :nodes="tree" />
      <p class="mt-3 text-xs text-ink-soft">{{ caption }} A colon in a title becomes “ - ” so every system accepts it.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NamingPreset } from '@/api/client'
import FileTree from '@/components/shared/FileTree.vue'
import { layoutTree } from '@/lib/layouts'

/** What the example library looks like on disk with a layout. */
const props = withDefaults(defineProps<{ layout: NamingPreset; title?: string }>(), { title: 'Your library would look like' })

const tree = computed(() => layoutTree(props.layout))

const CAPTIONS: Record<NamingPreset, string> = {
  title: 'No author folder, so the author comes from the tags inside each file.',
  author_folder: 'Each book sits in its own folder under its author. The ID in brackets keeps same-title books apart.',
  author_folder_year: 'The year sorts an author’s books by publication date.',
  author_series: 'Series books are numbered 01, 02 so they sort in order. Books with no series skip that folder.',
  author_series_year: 'Series books are numbered, then dated. Books with no series skip that folder.',
}
const caption = computed(() => CAPTIONS[props.layout])
</script>
