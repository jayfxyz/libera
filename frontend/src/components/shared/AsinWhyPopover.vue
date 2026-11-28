<template>
  <Popover>
    <PopoverTrigger as-child>
      <button
        type="button"
        class="inline-flex cursor-pointer items-center gap-1 rounded-md font-medium text-brand underline decoration-dotted underline-offset-2"
        aria-label="Why does Libera add the audiobook ID to names?"
      >
        <span>Why?</span>
        <InfoIcon class="size-3.5 shrink-0 opacity-70" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent align="start" class="text-sm">
      <p class="font-semibold text-ink">Why names end in the audiobook ID</p>
      <p class="mt-1 text-ink-soft">
        Every audiobook on Audible has its own ID (ASIN), such as <span class="font-mono text-xs">B002UZMLXM</span>.
        Libera now ends each book's folder and file name with it.
      </p>
      <ul class="mt-1.5 list-disc space-y-1 pl-4 text-ink-soft">
        <li>
          Different books can share a title, like books in a series with the same name or several recordings of
          one book. The ID keeps them apart.
        </li>
        <li>
          When Libera looks for files already on disk, it matches them to books by ID rather than by title, so a
          file is never mistaken for another book with the same name.
        </li>
        <li>
          Libation names books the same way, and Audiobookshelf reads the
          <span class="font-mono text-xs">[ASIN]</span> from the folder name to match the book.
        </li>
        <li>
          Really can't stand the ID in your file names?
          <a :href="FEATURE_REQUEST_URL" target="_blank" rel="noopener" class="text-brand underline underline-offset-2">Open a feature request on GitHub</a>
          and tell us why.
        </li>
      </ul>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { InfoIcon } from '@lucide/vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const FEATURE_REQUEST_URL = 'https://github.com/jayfxyz/libera/issues'
</script>
