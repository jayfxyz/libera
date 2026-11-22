<template>
  <div class="min-w-0 flex-1 overflow-y-auto">
    <div class="flex max-w-[900px] flex-col gap-[18px] px-4 pt-5 pb-12 md:px-9 md:pt-7">
      <header>
        <h1 class="page-title">Downloads</h1>
        <p class="mt-1 text-sm text-ink-soft">{{ active.length }} in progress · {{ finished.length }} finished</p>
      </header>

      <div v-if="jobs.length === 0" class="card flex flex-col items-center gap-2 px-6 py-12 text-center">
        <DownloadIcon class="size-8 text-ink-faint" aria-hidden="true" />
        <p class="font-semibold">Nothing downloading</p>
        <p class="text-sm text-ink-soft">Pick books in the <RouterLink to="/library" class="underline">Library</RouterLink> to download them.</p>
      </div>

      <section v-for="group in groups" v-show="group.jobs.length" :key="group.title" :aria-label="group.title" class="flex flex-col gap-2">
        <div class="flex items-end justify-between gap-2">
          <h2 class="eyebrow">{{ group.title }}</h2>
          <button
            v-if="group.title === 'Finished' && retryable.length"
            type="button"
            class="btn-secondary h-9 px-3 text-[13px]"
            :disabled="retryingAll"
            @click="retryAll"
          >Retry all failed ({{ retryable.length }})</button>
        </div>
        <ul class="card overflow-hidden">
          <li v-for="job in group.jobs" :key="job.id" class="flex items-start gap-3.5 border-b border-line-faint p-3 last:border-b-0 sm:px-4">
            <BookCover :src="coverFor(job.book_id)" :title="titleFor(job)" size="sm" rounded="rounded-lg" class="w-12 shrink-0" />
            <div class="flex min-w-0 flex-1 flex-col gap-1">
              <div class="flex items-start justify-between gap-2">
                <span class="text-[15px] font-semibold leading-[1.3]">
                  {{ titleFor(job) }}
                </span>
                <button
                  v-if="isActive(job)"
                  type="button"
                  class="btn-secondary h-9 shrink-0 px-3 text-[13px]"
                  :aria-label="`Cancel ${titleFor(job)}`"
                  @click="downloads.cancel(job.id)"
                >Cancel</button>
                <button
                  v-if="job.status === 'failed'"
                  type="button"
                  class="btn-secondary h-9 shrink-0 px-3 text-[13px]"
                  :aria-label="`Retry ${titleFor(job)}`"
                  @click="downloads.retry(job.id)"
                >Retry</button>
              </div>
              <span class="flex items-center gap-1.5 text-xs font-semibold" :class="tone(job).text">
                <span class="size-2 shrink-0 rounded-full" :class="tone(job).dot" />{{ label(job) }}
                <span v-if="job.finished_at" class="font-normal text-ink-soft">· {{ ago(job.finished_at) }}</span>
              </span>
              <div v-if="job.status === 'downloading' || job.status === 'decrypting'" class="h-1 overflow-hidden rounded-full bg-busy-track">
                <div class="h-1 bg-busy transition-[width]" :style="{ width: `${Math.round(job.percent)}%` }" />
              </div>
              <p v-if="job.message && ['done', 'failed', 'queued'].includes(job.status)" class="text-xs break-words" :class="job.status === 'failed' ? 'text-warn-deep' : job.status === 'done' ? 'font-mono text-ink-soft' : 'text-ink-soft'">
                {{ job.message }}<template v-if="job.status === 'queued' && job.retry_at"> Next try at {{ clock(job.retry_at) }}.</template>
              </p>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { DownloadIcon } from '@lucide/vue'
import type { Download } from '@/api/client'
import BookCover from '@/components/library/BookCover.vue'
import { isActive } from '@/lib/bookStatus'
import { useDownloadsStore } from '@/stores/downloads'
import { useLibraryStore } from '@/stores/library'

const downloads = useDownloadsStore()
const library = useLibraryStore()

// Covers and titles come from the library.
onMounted(() => {
  if (library.books.length === 0) library.fetchBooks()
})

const jobs = computed(() => Array.from(downloads.byId.values()))
const active = computed(() => {
  const order = { downloading: 0, decrypting: 0, queued: 1 } as Record<string, number>
  return jobs.value.filter((j) => isActive(j)).sort((a, b) => (order[a.status] ?? 2) - (order[b.status] ?? 2))
})
// Newest first; history survives restarts (the server keeps the last 500).
const finished = computed(() =>
  jobs.value.filter((j): boolean => !isActive(j)).sort((a, b) => (b.finished_at ?? '').localeCompare(a.finished_at ?? '')),
)
const groups = computed(() => [
  { title: 'In progress', jobs: active.value },
  { title: 'Finished', jobs: finished.value },
])

function bookFor(id: number) {
  return library.books.find((b) => b.id === id)
}
function titleFor(job: Download) {
  return job.title || bookFor(job.book_id)?.title || `Book #${job.book_id}`
}
function coverFor(id: number) {
  return bookFor(id)?.cover_url ?? ''
}

function label(job: Download) {
  switch (job.status) {
    case 'queued': return 'Queued'
    case 'downloading': return `Downloading · ${Math.round(job.percent)}%`
    case 'decrypting': return job.message || 'Decrypting'
    case 'done': return `Downloaded${job.format ? ` · ${job.format.toUpperCase()}` : ''}`
    case 'cancelled': return 'Cancelled'
    default: return 'Failed'
  }
}

/** "14:30", in the viewer's time zone. */
function clock(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

const retryable = computed(() => downloads.retryable())
const retryingAll = ref(false)
async function retryAll() {
  retryingAll.value = true
  try {
    await downloads.retryFailed()
  } finally {
    retryingAll.value = false
  }
}

function ago(iso: string) {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function tone(job: Download) {
  if (job.status === 'done') return { text: 'text-ok-ink', dot: 'bg-ok' }
  if (job.status === 'cancelled') return { text: 'text-ink-soft', dot: 'bg-line' }
  if (job.status === 'failed') return { text: 'text-warn-ink', dot: 'bg-warn' }
  if (job.status === 'queued') return { text: 'text-ink-soft', dot: 'bg-ink-faint' }
  return { text: 'text-busy', dot: 'bg-busy' }
}
</script>
