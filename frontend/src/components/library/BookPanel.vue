<template>
  <!-- Below xl the panel overlays the page; from xl it sits beside the list. -->
  <div class="fixed inset-0 z-30 bg-black/30 xl:hidden" aria-hidden="true" @click="emit('close')" />
  <aside
    aria-label="Book details"
    class="fixed inset-y-0 right-0 z-40 flex w-full flex-col bg-surface shadow-xl sm:w-[420px] xl:static xl:z-auto xl:w-[400px] xl:shrink-0 xl:border-l xl:border-line-soft xl:shadow-none"
  >
    <div class="flex shrink-0 items-center justify-between px-6 pt-5 pb-3">
      <span class="eyebrow">Book</span>
      <button type="button" class="btn-secondary size-10 px-0 text-ink-soft" aria-label="Close details" @click="emit('close')">
        <XIcon class="size-4" />
      </button>
    </div>

    <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-soft">Loading…</div>
    <div v-else-if="loadError" class="p-6 text-sm text-warn-deep">{{ loadError }}</div>

    <!-- [&>*]:shrink-0: in a scrolling column nothing may shrink (the cover has no height of its own). -->
    <div v-else-if="book" class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-6 pb-[calc(2rem+env(safe-area-inset-bottom))] [&>*]:shrink-0">
      <BookCover :src="book.cover_url" :title="book.title" :author="book.authors[0]" size="lg" rounded="rounded-xl" />

      <div class="flex flex-col gap-1.5">
        <h2 class="font-display text-2xl font-bold leading-[1.15] tracking-[-0.01em]">{{ book.title }}</h2>
        <p v-if="book.subtitle" class="text-sm text-ink-soft">{{ book.subtitle }}</p>
        <p v-if="book.authors.length" class="text-sm text-ink-soft">by <strong class="font-semibold text-ink">{{ book.authors.join(', ') }}</strong></p>
        <p v-if="book.narrators.length" class="text-sm text-ink-soft">read by <strong class="font-semibold text-ink">{{ book.narrators.join(', ') }}</strong></p>
        <p class="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-ink-soft">
          <span>{{ formatDuration(book.length_minutes) }}</span>
          <span v-if="book.series.length">{{ book.series[0]!.name }}<template v-if="book.series[0]!.index"> #{{ book.series[0]!.index }}</template></span>
          <span v-if="book.audible_rating">★ {{ book.audible_rating.toFixed(1) }}</span>
          <span v-if="book.publisher">{{ book.publisher }}</span>
        </p>
      </div>

      <!-- What can be done now depends on the book's state. -->
      <div v-if="status.state === 'none'" class="flex flex-wrap gap-2">
        <button type="button" class="btn-primary flex-1" :disabled="busy" @click="download">Download</button>
        <button v-if="hasPdf" type="button" class="btn-secondary" :disabled="busy" @click="savePdf">
          {{ savingPdf ? 'Saving PDF…' : 'PDF only' }}
        </button>
      </div>

      <div v-else-if="status.state === 'downloading'" class="flex flex-col gap-2 rounded-xl bg-busy-soft p-3.5">
        <div class="flex justify-between text-[13px] font-semibold text-busy">
          <span>{{ job?.status === 'decrypting' ? 'Decrypting' : 'Downloading' }}</span>
          <span class="font-mono">{{ status.percent }}%</span>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-[#D3DDF7]">
          <div class="h-1.5 bg-busy transition-[width]" :style="{ width: `${status.percent}%` }" />
        </div>
        <button type="button" class="btn self-start h-9 border border-busy-line bg-surface px-3 text-[13px] text-ink" @click="cancel">Cancel</button>
      </div>

      <div v-else-if="status.state === 'queued'" class="flex flex-col gap-2.5">
        <span class="inline-flex h-7 items-center self-start rounded-full border border-dashed border-ink-faint px-2.5 text-xs font-semibold text-ink-soft">{{ status.label }}</span>
        <button type="button" class="btn-secondary self-start" @click="cancel">Cancel</button>
      </div>

      <div v-else-if="status.state === 'unavailable'" class="flex items-center justify-between gap-2 rounded-xl border border-line-soft bg-paper px-3.5 py-3">
        <UnavailablePopover />
      </div>

      <div v-else-if="status.state === 'error'" class="flex flex-col gap-2.5 rounded-xl bg-warn-soft p-3.5">
        <p class="text-[13px] leading-normal text-warn-deep">
          <strong>The last download failed.</strong>
          <template v-if="job?.status === 'failed' && job.message"> {{ job.message }}</template>
        </p>
        <button type="button" class="btn-primary h-10 self-start text-[13px]" :disabled="busy" @click="tryAgain">Try again</button>
      </div>

      <div v-else class="flex flex-col gap-2.5">
        <span class="inline-flex h-7 items-center gap-1.5 self-start rounded-full bg-ok-soft px-2.5 text-xs font-semibold text-ok-ink">{{ status.label }}</span>
        <div class="flex flex-wrap items-center gap-2">
          <button v-if="isDownloadable" type="button" class="btn-secondary" :disabled="busy" @click="download">Download again</button>
          <UnavailablePopover v-else />
          <button v-if="hasPdf" type="button" class="btn-secondary" :disabled="busy" @click="savePdf">
            {{ savingPdf ? 'Saving PDF…' : 'PDF only' }}
          </button>
        </div>
      </div>
      <p v-if="actionError" class="-mt-2 text-xs text-warn-deep">{{ actionError }}</p>
      <p v-else-if="notice" class="-mt-2 text-xs text-ok-ink break-all">{{ notice }}</p>

      <div v-if="status.state !== 'unavailable' || book.file_path" class="flex flex-col gap-1.5">
        <!-- Downloads from before paths were recorded only have the computed location. -->
        <span class="text-xs font-semibold text-ink-soft">{{ book.file_path ? 'Saved to' : status.state === 'downloaded' ? 'Expected location' : 'Will save to' }}</span>
        <code class="block rounded-[10px] bg-paper px-3 py-2.5 font-mono text-xs leading-normal break-all">{{ book.file_path || book.planned_path }}</code>
      </div>

      <div v-if="isDownloadable" class="flex flex-col gap-1 border-t border-line-faint pt-4">
        <label class="flex flex-col gap-1.5 text-xs font-semibold text-ink-soft">
          Format for this book
          <SelectField v-model="format" :options="formatOptions" />
        </label>
        <!-- Collapsed: splitting is rarely wanted. -->
        <details class="group">
          <summary class="flex min-h-11 cursor-pointer list-none items-center gap-1.5 text-xs font-semibold text-ink-soft transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
            <ChevronRightIcon class="size-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />Advanced
          </summary>
          <div class="flex min-h-11 flex-wrap items-center gap-x-1.5 pl-5 text-sm">
            <label class="flex cursor-pointer items-center gap-2.5">
              <input v-model="splitChapters" type="checkbox" class="checkbox" />Split by chapter
            </label>
            <SplitChaptersPopover />
          </div>
        </details>
        <p class="text-xs text-ink-soft">The companion PDF is saved too, when the book has one.</p>
      </div>

      <div v-if="book.genres.length" class="flex flex-col gap-2 border-t border-line-faint pt-4">
        <span class="text-xs font-semibold text-ink-soft">Genres <span class="font-normal">· from Audible</span></span>
        <div class="flex flex-wrap gap-1.5">
          <span v-for="g in book.genres" :key="g" class="chip h-[30px] px-2.5 text-xs">{{ g }}</span>
        </div>
      </div>

      <div class="border-t border-line-faint pt-4">
        <button type="button" class="btn-secondary w-full" @click="toggleHidden">
          <component :is="book.is_hidden ? EyeIcon : EyeOffIcon" class="size-4" />
          {{ book.is_hidden ? 'Show in library' : 'Hide from library' }}
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRightIcon, EyeIcon, EyeOffIcon, XIcon } from '@lucide/vue'
import type { BookDetail } from '@/api/client'
import { api } from '@/api/client'
import { SelectField, type SelectOption } from '@/components/ui/select'
import { bookStatus, formatDuration } from '@/lib/bookStatus'
import { useDownloadsStore } from '@/stores/downloads'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import BookCover from './BookCover.vue'
import SplitChaptersPopover from './SplitChaptersPopover.vue'
import UnavailablePopover from './UnavailablePopover.vue'

const props = defineProps<{ bookId: number }>()
const emit = defineEmits<{ close: [] }>()

const downloads = useDownloadsStore()
const library = useLibraryStore()
const settings = useSettingsStore()

const book = ref<BookDetail | null>(null)
const loading = ref(true)
const loadError = ref('')
const busy = ref(false)
const actionError = ref('')
const notice = ref('')
const savingPdf = ref(false)
const format = ref<'default' | 'm4b' | 'mp3'>('default')
const formatOptions = computed<SelectOption<'default' | 'm4b' | 'mp3'>[]>(() => [
  { value: 'default', label: `Default — ${settings.defaultFormat.toUpperCase()}${settings.defaultFormat === 'm4b' ? ', original' : ''}` },
  { value: 'm4b', label: 'M4B (original, no re-encode)' },
  { value: 'mp3', label: 'MP3 (re-encode)' },
])
const splitChapters = ref(false)

async function load() {
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try {
    book.value = await api.library.get(props.bookId)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
watch(() => props.bookId, load, { immediate: true })

const job = computed(() => downloads.latestFor(props.bookId))
// The list's copy is updated live by download events; the detail is fetched once.
const summary = computed(() => library.books.find((b) => b.id === props.bookId))
// The list's copy is the fresher one after a sync; null means "not known yet".
const hasPdf = computed(() => (summary.value ?? book.value)?.has_pdf === true)
const isDownloadable = computed(() => (summary.value ?? book.value)?.is_downloadable !== false)
const status = computed(() =>
  bookStatus(summary.value ?? book.value ?? { download_status: 'not_downloaded', last_format: null, is_downloadable: true }, job.value),
)
// Refresh the saved path once a download finishes.
watch(() => status.value.state, (now, before) => {
  if (now === 'downloaded' && before === 'downloading') load()
})

function enqueue() {
  const b = book.value!
  return downloads.enqueue(b.id, { format: format.value === 'default' ? undefined : format.value, split_chapters: splitChapters.value }, b.title)
}

async function download() {
  if (book.value) await act(enqueue)
}

/** Retry the failed download (reusing what it already fetched), or queue a new one. */
async function tryAgain() {
  if (!book.value) return
  const failed = job.value?.status === 'failed' ? job.value : undefined
  await act(() => (failed ? downloads.retry(failed.id) : enqueue()))
}

async function savePdf() {
  if (!book.value) return
  const id = book.value.id
  savingPdf.value = true
  await act(async () => {
    const { file_path } = await api.library.savePdf(id)
    notice.value = `PDF saved to ${file_path}`
  })
  savingPdf.value = false
}

async function act(action: () => Promise<unknown>) {
  busy.value = true
  actionError.value = ''
  notice.value = ''
  try {
    await action()
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function cancel() {
  if (job.value) await downloads.cancel(job.value.id)
}

// --- hidden
async function toggleHidden() {
  if (!book.value) return
  const value = !book.value.is_hidden
  await library.setHidden([book.value.id], value)
  book.value.is_hidden = value
}
</script>
