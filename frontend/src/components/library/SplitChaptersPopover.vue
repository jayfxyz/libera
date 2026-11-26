<template>
  <Popover>
    <PopoverTrigger as-child>
      <button
        type="button"
        class="inline-flex cursor-pointer items-center gap-1 rounded-md text-xs font-medium text-ink-soft underline decoration-dotted underline-offset-2 transition-colors hover:text-ink"
        aria-label="Why is splitting by chapter not recommended?"
      >
        <span>(not recommended)</span>
        <InfoIcon class="size-3.5 shrink-0 opacity-70" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent align="start">
      <p class="font-semibold text-ink">Why splitting isn't recommended</p>
      <p class="mt-1 text-ink-soft">
        The audiobook file already has its chapters built in, and Audiobookshelf and most players
        let you jump between them without splitting anything.
      </p>
      <ul class="mt-1.5 list-disc space-y-1 pl-4 text-ink-soft">
        <li>
          Every chapter becomes its own file next to the full audiobook, so the book takes extra
          disk space.
        </li>
        <li>
          Some library tools then treat the folder as a multi-track book instead of a single file.
        </li>
        <li>
          It takes longer, and a chapter that fails is skipped, which can leave an incomplete set.
        </li>
      </ul>
      <p class="mt-1.5 text-ink-soft">
        Use it only if your player can't read chapters from a single file, as some car stereos and
        MP3 players can't.
      </p>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { InfoIcon } from '@lucide/vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
</script>
