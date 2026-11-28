<template>
  <ul class="font-mono text-xs leading-relaxed" :class="depth > 0 ? 'ml-2 border-l border-line pl-3.5' : ''">
    <li v-for="node in nodes" :key="`${node.kind}:${node.name}`">
      <span class="flex items-start gap-1.5" :class="node.kind === 'folder' ? 'font-semibold text-ink' : node.kind === 'audio' ? 'text-ink' : 'text-ink-soft'">
        <component :is="icons[node.kind]" class="mt-[3px] size-3.5 shrink-0" :class="node.kind === 'folder' ? 'text-brand' : ''" aria-hidden="true" />
        <span class="min-w-0 break-words">{{ node.name }}</span>
        <span v-if="node.size !== undefined" class="ml-auto shrink-0 pl-2 font-normal text-ink-faint">{{ formatBytes(node.size) }}</span>
      </span>
      <FileTree v-if="node.children.length" :nodes="node.children" :depth="depth + 1" />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { FileIcon, FileTextIcon, FolderIcon, ImageIcon, MusicIcon } from '@lucide/vue'
import { formatBytes, type TreeNode } from '@/lib/fileTree'

/** Folders and files as an indented tree: the layout preview, and the files a book has on disk. */
withDefaults(defineProps<{ nodes: TreeNode[]; depth?: number }>(), { depth: 0 })

const icons = { folder: FolderIcon, audio: MusicIcon, cover: ImageIcon, pdf: FileTextIcon, other: FileIcon }
</script>
