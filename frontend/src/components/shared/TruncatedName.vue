<template>
  <span class="flex min-w-0" :title="name">
    <span class="truncate">{{ parts.head }}</span><span class="shrink-0 whitespace-pre">{{ parts.tail }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { splitName } from '@/lib/fileTree'

/** A file name or path on one line: a long one is cut in the middle ("…"), and its [ID] and extension always show. */
const props = defineProps<{ name: string }>()

const parts = computed(() => splitName(props.name))
</script>
