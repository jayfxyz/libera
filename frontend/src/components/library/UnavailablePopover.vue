<template>
  <Popover>
    <PopoverTrigger as-child>
      <button
        type="button"
        :class="triggerClass"
        :aria-label="ariaLabel"
        @click.stop
      >
        <slot>
          <LockIcon class="size-3.5 shrink-0" aria-hidden="true" />
          <span>Not downloadable</span>
          <InfoIcon class="size-3.5 shrink-0 opacity-70" aria-hidden="true" />
        </slot>
      </button>
    </PopoverTrigger>
    <PopoverContent :align="align" @click.stop>
      <p class="font-semibold text-ink">Not downloadable from Audible</p>
      <p class="mt-1 text-ink-soft">
        Audible reports this account doesn't have offline download rights for this title — usually because it was
        borrowed through Audible Plus or Amazon Music Unlimited and is no longer active.
      </p>
      <p class="mt-1.5 text-ink-soft">
        If you purchase it or renew access, rescan your library to enable downloading.
      </p>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { InfoIcon, LockIcon } from '@lucide/vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

withDefaults(
  defineProps<{
    align?: 'start' | 'center' | 'end'
    triggerClass?: string
    ariaLabel?: string
  }>(),
  {
    align: 'start',
    triggerClass: 'inline-flex cursor-pointer items-center gap-1.5 rounded-md text-xs font-semibold text-ink-soft transition-colors hover:text-ink',
    ariaLabel: 'Why is this book not downloadable?',
  },
)
</script>
