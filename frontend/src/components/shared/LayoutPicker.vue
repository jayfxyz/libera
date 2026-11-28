<template>
  <div class="grid min-w-0 gap-6 md:grid-cols-2">
    <div class="flex min-w-0 flex-col gap-2">
      <h3 class="font-mono text-[11px] font-semibold tracking-wider text-ink-soft uppercase">Choose a layout</h3>
      <div role="radiogroup" aria-label="Folder layout" class="flex flex-col gap-2">
        <LayoutOption v-for="layout in mainLayouts" :key="layout.id" :layout="layout" :selected="model" :name="groupName" @pick="model = $event" />
        <details class="group" :open="otherLayouts.some((layout) => layout.id === model)">
          <summary class="flex cursor-pointer list-none items-center gap-1.5 rounded-md px-0.5 py-1.5 text-sm font-semibold text-ink-soft hover:text-ink">
            <ChevronRightIcon class="size-4 transition-transform group-open:rotate-90" aria-hidden="true" />Other options
          </summary>
          <div class="mt-1 flex flex-col gap-2">
            <LayoutOption v-for="layout in otherLayouts" :key="layout.id" :layout="layout" :selected="model" :name="groupName" @pick="model = $event" />
          </div>
        </details>
      </div>
    </div>

    <div class="flex min-w-0 flex-col gap-2">
      <h3 class="font-mono text-[11px] font-semibold tracking-wider text-ink-soft uppercase">Your library would look like</h3>
      <div class="min-w-0 rounded-[10px] border border-line bg-paper p-4">
        <div class="mb-2 flex justify-between gap-2 font-mono text-[10px] text-ink-soft">
          <span>/audiobooks</span><span>example books</span>
        </div>
        <FileTree :nodes="tree" />
        <p class="mt-3 text-xs text-ink-soft">{{ caption }} A colon in a title becomes “ - ” so every system accepts it.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import { ChevronRightIcon } from '@lucide/vue'
import type { NamingPreset } from '@/api/client'
import LayoutOption from '@/components/shared/LayoutOption.vue'
import FileTree from '@/components/shared/FileTree.vue'
import { LAYOUTS, layoutTree } from '@/lib/layouts'

/** Picks a folder layout and shows what the library looks like with it. Used by the welcome dialog and by Settings. */
const model = defineModel<NamingPreset>({ required: true })

// Two pickers can be on screen at once (Settings and the dialog opened from it), so each has its own radio group.
const groupName = `layout-${useId()}`

const mainLayouts = LAYOUTS.filter((layout) => !layout.other)
const otherLayouts = LAYOUTS.filter((layout) => layout.other)
const tree = computed(() => layoutTree(model.value))

const CAPTIONS: Record<NamingPreset, string> = {
  title: 'No author folder, so the author comes from the tags inside each file.',
  author_folder: 'Each book sits in its own folder under its author. The ID in brackets keeps same-title books apart.',
  author_folder_year: 'The year sorts an author’s books by publication date.',
  author_series: 'Series books are numbered 01, 02 so they sort in order. Books with no series skip that folder.',
  author_series_year: 'Series books are numbered, then dated. Books with no series skip that folder.',
}
const caption = computed(() => CAPTIONS[model.value])
</script>
