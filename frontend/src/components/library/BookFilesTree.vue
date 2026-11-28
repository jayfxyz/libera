<template>
  <div class="min-w-0 rounded-[10px] border border-line bg-paper p-3.5">
    <div class="mb-2 flex justify-between gap-2 font-mono text-[10px] text-ink-soft">
      <span class="min-w-0 break-all">{{ files.root }}</span>
      <span class="shrink-0">{{ files.found ? summary : "expected" }}</span>
    </div>
    <FileTree :nodes="tree" :ghost="!files.found" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BookFiles } from '@/api/client'
import FileTree from '@/components/shared/FileTree.vue'
import { bookFilesTree, formatBytes } from '@/lib/fileTree'

const props = defineProps<{ files: BookFiles }>()

const tree = computed(() => bookFilesTree(props.files))
const summary = computed(() => {
  const count = props.files.files.length
  const total = props.files.files.reduce((sum, file) => sum + file.size_bytes, 0)
  return `${count} ${count === 1 ? 'file' : 'files'} · ${formatBytes(total)}`
})
</script>
