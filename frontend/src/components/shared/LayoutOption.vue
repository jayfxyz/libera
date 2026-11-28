<template>
  <label
    class="relative block cursor-pointer rounded-[10px] border py-2.5 pr-3.5 pl-10 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand"
    :class="selected === layout.id ? 'border-brand bg-brand/10' : 'border-line bg-surface hover:border-ink-soft'"
  >
    <input
      type="radio"
      :name="name"
      class="absolute top-3.5 left-3.5 size-4 accent-brand"
      :value="layout.id"
      :checked="selected === layout.id"
      @change="emit('pick', layout.id)"
    />
    <span class="flex flex-wrap items-center gap-2">
      <span class="font-semibold">{{ layout.name }}</span>
      <span v-if="layout.recommended" class="rounded-full bg-ok-soft px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-ok-ink uppercase">Recommended</span>
    </span>
    <span class="block text-xs text-ink-soft">{{ layout.why }}</span>
  </label>
</template>

<script setup lang="ts">
import type { NamingPreset } from '@/api/client'
import type { Layout } from '@/lib/layouts'

defineProps<{ layout: Layout; selected: NamingPreset; name: string }>()
const emit = defineEmits<{ pick: [id: NamingPreset] }>()
</script>
