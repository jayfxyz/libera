<template>
  <ul class="font-mono text-xs leading-relaxed" :class="depth > 0 ? 'ml-2 border-l border-line pl-3.5' : ''">
    <li v-for="node in nodes" :key="`${node.kind}:${node.name}`">
      <span class="flex items-start gap-1.5" :class="[ghost ? 'text-ink-soft' : node.kind === 'folder' ? 'font-semibold text-ink' : node.kind === 'audio' ? 'text-ink' : 'text-ink-soft', ghost && node.kind !== 'folder' ? 'italic' : '']">
        <component :is="icons[node.kind]" class="mt-[3px] size-3.5 shrink-0" :class="node.kind === 'folder' ? 'text-brand' : ''" aria-hidden="true" />
        <TruncatedName :name="node.name" class="flex-1" />
        <span v-if="node.size !== undefined" class="shrink-0 pl-2 font-normal text-ink-faint">{{ formatBytes(node.size) }}</span>
      </span>
      <FileTree v-if="node.children.length" :nodes="node.children" :depth="depth + 1" :ghost="ghost" />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { FileIcon, FileTextIcon, FolderIcon, ImageIcon, MusicIcon } from '@lucide/vue'
import TruncatedName from '@/components/shared/TruncatedName.vue'
import { formatBytes, type TreeNode } from '@/lib/fileTree'

/** Folders and files as an indented tree: the layout preview, and the files a book has on disk. */
/** ghost: draw it faded and italic, for files that are not there yet. */
withDefaults(defineProps<{ nodes: TreeNode[]; depth?: number; ghost?: boolean }>(), { depth: 0, ghost: false })

const icons = { folder: FolderIcon, audio: MusicIcon, cover: ImageIcon, pdf: FileTextIcon, other: FileIcon }
</script>
