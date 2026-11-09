<template>
  <!-- Real artwork when Audible has it; otherwise the design's typographic tile. -->
  <span
    class="relative block aspect-square overflow-hidden"
    :class="[rounded, showTile ? 'shadow-[inset_0_0_0_1px_rgba(18,20,24,0.10)]' : '']"
    :style="showTile ? { background: tile.bg } : undefined"
  >
    <img
      v-if="src && !failed"
      :src="src"
      alt=""
      loading="lazy"
      decoding="async"
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <span
      v-else
      class="absolute inset-0 flex flex-col justify-end gap-1.5"
      :class="size === 'lg' ? 'p-6' : size === 'sm' ? 'p-1.5' : 'p-3'"
      :style="{ color: tile.fg }"
      aria-hidden="true"
    >
      <span
        class="font-display font-bold leading-[1.05] overflow-hidden"
        :class="size === 'lg' ? 'text-[30px] tracking-[-0.015em]' : size === 'sm' ? 'text-[8px] max-h-[26px]' : 'text-[17px]'"
      >{{ title }}</span>
      <span v-if="author && size !== 'sm'" class="text-[10px] font-semibold uppercase tracking-[0.08em]">{{ author }}</span>
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  src?: string
  title: string
  author?: string
  size?: 'sm' | 'md' | 'lg'
  rounded?: string
}>(), { size: 'md', rounded: 'rounded-[10px]', src: '', author: '' })

const failed = ref(false)
watch(() => props.src, () => (failed.value = false))
const showTile = computed(() => !props.src || failed.value)

// Background/ink pairs from the design's placeholder covers.
const TILES = [
  { bg: '#EDE6DF', fg: '#7A2E1F' }, { bg: '#F2C230', fg: '#1B1B1B' }, { bg: '#F4F0E2', fg: '#6B4F1D' },
  { bg: '#1C1C1C', fg: '#F2B705' }, { bg: '#DDEBF3', fg: '#1F3A4D' }, { bg: '#23272E', fg: '#F0C64B' },
  { bg: '#E9BF8C', fg: '#1D3557' }, { bg: '#2F6F9E', fg: '#FFFFFF' }, { bg: '#232A6B', fg: '#E8B04B' },
  { bg: '#8FB3E0', fg: '#121418' }, { bg: '#1E3A5F', fg: '#F4F1E8' }, { bg: '#EEF2E6', fg: '#2F6B3A' },
]
const tile = computed(() => {
  let h = 0
  for (const ch of props.title) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return TILES[h % TILES.length]!
})
</script>
