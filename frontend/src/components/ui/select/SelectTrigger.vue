<script setup lang="ts">
import type { SelectTriggerProps } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
import { ChevronDownIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { SelectIcon, SelectTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

/** box: a form field, like `textbox`. inline: borderless, inside a labelled `field` (the library toolbar). */
const props = withDefaults(
  defineProps<SelectTriggerProps & { class?: HTMLAttributes['class'], variant?: 'box' | 'inline' }>(),
  { variant: 'box' },
)

const delegatedProps = reactiveOmit(props, 'class', 'variant')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectTrigger
    data-slot="select-trigger"
    v-bind="forwardedProps"
    :class="cn(
      'flex min-w-0 cursor-pointer items-center justify-between gap-2 text-ink outline-none select-none data-disabled:cursor-not-allowed data-disabled:opacity-60 *:data-[slot=select-value]:truncate',
      variant === 'box'
        ? 'h-11 w-full rounded-[10px] border border-line bg-surface px-3 text-left text-sm focus-visible:border-brand'
        : 'h-10 flex-1 bg-transparent pr-1 text-[13px] font-semibold',
      props.class,
    )"
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDownIcon class="pointer-events-none size-4 shrink-0 text-ink-soft" />
    </SelectIcon>
  </SelectTrigger>
</template>
