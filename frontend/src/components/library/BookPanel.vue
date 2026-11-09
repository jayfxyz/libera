<template>
  <!-- Below xl the panel overlays the page; from xl it sits beside the list. -->
  <div class="fixed inset-0 z-30 bg-ink/20 xl:hidden" aria-hidden="true" @click="emit('close')" />
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
        <button type="button" class="btn-primary flex-1" :disabled="busy" @click="download('audio')">Download</button>
        <button type="button" class="btn-secondary" :disabled="busy" @click="download('pdf')">PDF only</button>
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
        <span class="inline-flex h-7 items-center self-start rounded-full border border-dashed border-ink-faint px-2.5 text-xs font-semibold text-ink-soft">Queued</span>
        <button type="button" class="btn-secondary self-start" @click="cancel">Cancel</button>
      </div>

      <div v-else-if="status.state === 'error'" class="flex flex-col gap-2.5 rounded-xl bg-warn-soft p-3.5">
        <p class="text-[13px] leading-normal text-warn-deep">
          <strong>The last download failed.</strong>
          <template v-if="job?.status === 'error' && job.message"> {{ job.message }}</template>
        </p>
        <button type="button" class="btn-primary h-10 self-start text-[13px]" :disabled="busy" @click="download('audio')">Try again</button>
      </div>

      <div v-else class="flex flex-col gap-2.5">
        <span class="inline-flex h-7 items-center gap-1.5 self-start rounded-full bg-ok-soft px-2.5 text-xs font-semibold text-ok-ink">{{ status.label }}</span>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn-secondary" :disabled="busy" @click="download('audio')">Download again</button>
          <button type="button" class="btn-secondary" :disabled="busy" @click="download('pdf')">PDF only</button>
        </div>
      </div>
      <p v-if="actionError" class="-mt-2 text-xs text-warn-deep">{{ actionError }}</p>

      <div class="flex flex-col gap-1.5">
        <!-- Downloads from before paths were recorded only have the computed location. -->
        <span class="text-xs font-semibold text-ink-soft">{{ book.file_path ? 'Saved to' : status.state === 'downloaded' ? 'Expected location' : 'Will save to' }}</span>
        <code class="block rounded-[10px] bg-paper px-3 py-2.5 font-mono text-xs leading-normal break-all">{{ book.file_path || book.planned_path }}</code>
      </div>

      <div class="flex flex-col gap-1 border-t border-line-faint pt-4">
        <label class="flex flex-col gap-1.5 text-xs font-semibold text-ink-soft">
          Format for this book
          <select v-model="format" class="textbox cursor-pointer font-medium">
            <option value="">Default — {{ settings.defaultFormat.toUpperCase() }}{{ settings.defaultFormat === 'm4b' ? ', original' : '' }}</option>
            <option value="m4b">M4B (original, no re-encode)</option>
            <option value="mp3">MP3 (re-encode)</option>
          </select>
        </label>
        <label class="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm">
          <input v-model="splitChapters" type="checkbox" class="checkbox" />Split by chapter
        </label>
        <label class="flex min-h-10 cursor-pointer items-center gap-2.5 text-sm">
          <input v-model="includePdf" type="checkbox" class="checkbox" />Companion PDF if available
        </label>
      </div>

      <div v-if="book.genres.length" class="flex flex-col gap-2 border-t border-line-faint pt-4">
        <span class="text-xs font-semibold text-ink-soft">Genres <span class="font-normal">· from Audible</span></span>
        <div class="flex flex-wrap gap-1.5">
          <span v-for="g in book.genres" :key="g" class="chip h-[30px] px-2.5 text-xs">{{ g }}</span>
        </div>
      </div>

      <div class="flex flex-col gap-2 border-t border-line-faint pt-4">
        <span class="text-xs font-semibold text-ink-soft">Your tags</span>
        <div class="flex flex-wrap items-center gap-1.5">
          <span v-for="t in tags" :key="t" class="inline-flex h-[30px] items-center gap-1 rounded-full bg-chip pl-2.5 pr-1 font-mono text-xs">
            {{ t }}
            <button type="button" class="flex size-6 items-center justify-center rounded-full hover:bg-line" :aria-label="`Remove tag ${t}`" @click="removeTag(t)">
              <XIcon class="size-3" />
            </button>
          </span>
          <input
            v-if="addingTag"
            ref="tagInput"
            v-model="newTag"
            class="h-[30px] w-32 rounded-full border border-line bg-surface px-2.5 font-mono text-xs outline-none focus:border-brand"
            placeholder="tag"
            aria-label="New tag"
            @keydown.enter.prevent="commitTag"
            @keydown.escape="addingTag = false"
            @blur="commitTag"
          />
          <button
            v-else
            type="button"
            class="h-[30px] cursor-pointer rounded-full border border-dashed border-[#B9BAB3] px-2.5 font-mono text-xs text-ink-soft"
            @click="startTag"
          >+ tag</button>
        </div>
      </div>

      <div class="flex flex-col gap-1 border-t border-line-faint pt-4">
        <div class="flex min-h-11 items-center justify-between gap-3">
          <span class="text-sm">Your rating</span>
          <span class="flex" role="radiogroup" aria-label="Your rating">
            <button
              v-for="star in 5"
              :key="star"
              type="button"
              role="radio"
              :aria-checked="(book.user_rating ?? 0) === star"
              :aria-label="`${star} star${star > 1 ? 's' : ''}`"
              class="flex size-9 cursor-pointer items-center justify-center"
              @click="setRating(star)"
            >
              <StarIcon class="size-5" :class="star <= (book.user_rating ?? 0) ? 'fill-[#F2B705] text-[#F2B705]' : 'text-line'" />
            </button>
          </span>
        </div>
        <label class="flex min-h-11 cursor-pointer items-center justify-between gap-3 text-sm">
          Finished
          <input type="checkbox" class="checkbox" :checked="book.is_finished" @change="toggleFinished" />
        </label>
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
import { computed, nextTick, ref, watch } from 'vue'
import { EyeIcon, EyeOffIcon, StarIcon, XIcon } from '@lucide/vue'
import type { BookDetail, JobKind } from '@/api/client'
import { api } from '@/api/client'
import { bookStatus, formatDuration, tagList } from '@/lib/bookStatus'
import { useDownloadsStore } from '@/stores/downloads'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import BookCover from './BookCover.vue'

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
const format = ref<'' | 'm4b' | 'mp3'>('')
const splitChapters = ref(false)
const includePdf = ref(true)

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

const job = computed(() => downloads.jobFor(props.bookId))
// The list's copy is updated live by download events; the detail is fetched once.
const summary = computed(() => library.books.find((b) => b.id === props.bookId))
const status = computed(() =>
  bookStatus(summary.value ?? book.value ?? { liberation_status: 'not_liberated', last_format: null }, job.value),
)
// Refresh the saved path once a download finishes.
watch(() => status.value.state, (now, before) => {
  if (now === 'downloaded' && before === 'downloading') load()
})

async function download(kind: JobKind) {
  if (!book.value) return
  busy.value = true
  actionError.value = ''
  try {
    await downloads.enqueue(book.value.id, {
      kind,
      format: format.value || undefined,
      split_chapters: splitChapters.value,
      include_pdf: includePdf.value,
    }, book.value.title)
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function cancel() {
  if (job.value) await downloads.cancel(job.value.job_id)
}

// --- your tags, rating, finished, hidden
const tags = computed(() => tagList(book.value?.tags ?? ''))
const addingTag = ref(false)
const newTag = ref('')
const tagInput = ref<HTMLInputElement | null>(null)

function startTag() {
  addingTag.value = true
  newTag.value = ''
  nextTick(() => tagInput.value?.focus())
}

async function commitTag() {
  if (!addingTag.value) return
  addingTag.value = false
  const tag = newTag.value.trim().replace(/\s+/g, '_')
  if (tag && !tags.value.includes(tag)) await saveTags([...tags.value, tag])
}

async function removeTag(tag: string) {
  await saveTags(tags.value.filter((t) => t !== tag))
}

async function saveTags(list: string[]) {
  if (!book.value) return
  const value = list.join(' ')
  await library.updateBook(book.value.id, { tags: value })
  book.value.tags = value
}

async function setRating(star: number) {
  if (!book.value) return
  const rating = book.value.user_rating === star ? 0 : star // tapping the current rating clears it
  await library.updateBook(book.value.id, { user_rating: rating })
  book.value.user_rating = rating || null
}

async function toggleFinished() {
  if (!book.value) return
  const value = !book.value.is_finished
  await library.updateBook(book.value.id, { is_finished: value })
  book.value.is_finished = value
}

async function toggleHidden() {
  if (!book.value) return
  const value = !book.value.is_hidden
  await library.setHidden([book.value.id], value)
  book.value.is_hidden = value
}
</script>
