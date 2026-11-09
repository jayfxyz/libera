<template>
  <div class="flex min-w-0 flex-1 overflow-hidden">
    <div class="min-w-0 flex-1 overflow-y-auto">
      <div class="mx-auto flex max-w-[1400px] flex-col gap-[18px] px-4 pt-5 pb-12 md:px-9 md:pt-7">
        <!-- Header -->
        <header class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 class="page-title">Library</h1>
            <p class="mt-1 text-sm text-ink-soft">{{ summaryLine }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <div ref="scanMenuEl" class="relative">
              <div class="flex overflow-hidden rounded-[10px] border border-line bg-surface">
                <button
                  type="button"
                  class="btn rounded-none px-3.5"
                  :disabled="scanning || !accounts.accounts.length"
                  :aria-label="scanLabel"
                  @click="scan(null)"
                >
                  <RefreshCwIcon class="size-4" :class="scanning ? 'animate-spin' : ''" />
                  <span class="hidden sm:inline">{{ scanLabel }}</span>
                </button>
                <button
                  v-if="accounts.accounts.length > 1"
                  type="button"
                  class="btn w-10 rounded-none border-l border-line-soft px-0"
                  aria-label="Scan one account"
                  aria-haspopup="menu"
                  :aria-expanded="scanMenuOpen"
                  :disabled="scanning"
                  @click="scanMenuOpen = !scanMenuOpen"
                >
                  <ChevronDownIcon class="size-3.5" />
                </button>
              </div>
              <div
                v-if="scanMenuOpen"
                role="menu"
                class="absolute right-0 top-full z-20 mt-1 min-w-56 rounded-[10px] border border-line bg-surface p-1 shadow-lg"
              >
                <button
                  v-for="a in accounts.accounts"
                  :key="a.id"
                  type="button"
                  role="menuitem"
                  class="flex h-10 w-full cursor-pointer items-center rounded-lg px-3 text-left text-sm hover:bg-paper"
                  @click="scan(a.id)"
                >Scan {{ accountLabel(a) }}</button>
              </div>
            </div>
            <button
              type="button"
              class="btn-primary"
              :disabled="library.downloadable.length === 0"
              @click="askDownload(library.downloadable)"
            >Download all ({{ library.downloadable.length }})</button>
          </div>
        </header>
        <p v-if="scanMessage" class="-mt-2 text-sm" :class="scanFailed ? 'text-warn-deep' : 'text-ink-soft'">{{ scanMessage }}</p>

        <!-- Toolbar -->
        <div class="flex flex-wrap gap-2">
          <!-- Phones: search + view on one row, sort/direction/account on the next. -->
          <label class="field order-1 min-w-0 flex-[1_1_200px] gap-2.5 px-3.5 sm:order-none sm:flex-[1_1_320px]">
            <SearchIcon class="size-[18px] shrink-0 text-ink-soft" aria-hidden="true" />
            <span class="sr-only">Search</span>
            <input
              v-model="query"
              type="search"
              placeholder="Search title, author or narrator"
              class="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-ink-faint"
              @input="onSearch"
            />
          </label>
          <label class="field order-3 min-w-[140px] flex-1 gap-1 pr-1 pl-3 text-[13px] text-ink-soft sm:order-none sm:flex-none">
            <span class="hidden sm:inline">Sort by</span>
            <select class="field-select min-w-0 flex-1" aria-label="Sort by" :value="library.sort" @change="library.setSort(($event.target as HTMLSelectElement).value as LibrarySort)">
              <option v-for="o in sortOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <button type="button" class="btn-secondary btn-icon order-4 text-base font-semibold sm:order-none" :aria-label="orderLabel" :title="orderLabel" @click="library.toggleOrder()">
            {{ library.order === 'asc' ? '↑' : '↓' }}
          </button>
          <label v-if="accounts.accounts.length > 1" class="field order-5 min-w-[140px] flex-1 gap-1 pr-1 pl-3 text-[13px] text-ink-soft sm:order-none sm:flex-none">
            <span class="hidden sm:inline">Account</span>
            <select class="field-select min-w-0 flex-1" aria-label="Account" :value="library.accountId ?? ''" @change="onAccount">
              <option value="">All accounts</option>
              <option v-for="a in accounts.accounts" :key="a.id" :value="a.id">{{ accountLabel(a) }}</option>
            </select>
          </label>
          <button
            type="button"
            class="order-2 sm:order-none"
            :class="library.selecting ? 'btn-ink' : 'btn-secondary'"
            :aria-pressed="library.selecting"
            @click="library.selecting ? library.clearSelection() : (library.selectMode = true)"
          >{{ library.selecting ? 'Done' : 'Select' }}</button>
          <div role="group" aria-label="View" class="order-2 flex overflow-hidden rounded-[10px] border border-line bg-surface sm:order-none">
            <button
              v-for="v in views"
              :key="v.value"
              type="button"
              class="flex h-[42px] w-11 cursor-pointer items-center justify-center"
              :class="library.view === v.value ? 'bg-ink text-white' : 'text-ink'"
              :aria-label="v.label"
              :aria-pressed="library.view === v.value"
              @click="library.view = v.value"
            >
              <component :is="v.icon" class="size-4" />
            </button>
          </div>
        </div>

        <!-- Status tabs -->
        <nav aria-label="Status" class="-mx-4 flex gap-1 overflow-x-auto border-b border-line-soft px-4 no-scrollbar md:mx-0 md:px-0">
          <button
            v-for="s in segments"
            :key="s.value"
            type="button"
            class="-mb-px flex h-10 shrink-0 cursor-pointer items-center gap-2 border-b-2 px-3 text-sm"
            :class="library.segment === s.value ? 'border-ink font-semibold text-ink' : 'border-transparent font-medium text-ink-soft'"
            :aria-current="library.segment === s.value ? 'true' : undefined"
            @click="library.segment = s.value"
          >
            {{ s.label }}
            <span
              class="rounded-full px-2 py-0.5 font-mono text-xs font-medium"
              :class="library.segment === s.value ? 'bg-ink text-white' : 'bg-chip text-ink'"
            >{{ library.segmentBooks[s.value].length }}</span>
          </button>
        </nav>

        <!-- Selection: only once a book is ticked (each row has its own checkbox). -->
        <div v-if="library.selecting" class="flex min-h-[52px] flex-wrap items-center gap-2">
          <label class="mr-auto flex h-11 cursor-pointer items-center gap-2.5 px-1 text-[13px] text-ink-soft">
            <input
              type="checkbox"
              class="checkbox"
              :checked="allVisibleSelected"
              :indeterminate="someVisibleSelected && !allVisibleSelected"
              :disabled="library.visibleBooks.length === 0"
              @change="library.selectAllVisible(!allVisibleSelected)"
            />
            <span>{{ allVisibleSelected ? `All ${library.visibleBooks.length} selected` : `Select all ${library.visibleBooks.length}` }}</span>
          </label>
          <div
            v-if="library.selected.size > 0"
            class="flex flex-wrap items-center gap-1.5 rounded-xl bg-ink py-1 pr-1 pl-3.5 text-white"
            role="toolbar"
            aria-label="Selected books"
          >
            <strong class="mr-1.5 text-[13px] font-semibold">{{ library.selected.size }} selected</strong>
            <button type="button" class="btn-primary h-9 rounded-lg px-3 text-[13px]" :disabled="selectionDownloadable.length === 0" @click="askDownload(selectionDownloadable)">
              Download {{ selectionDownloadable.length }}
            </button>
            <button type="button" class="btn h-9 rounded-lg border border-bar-line px-3 text-[13px]" @click="downloadPdfs">Download PDFs</button>
            <button type="button" class="btn h-9 rounded-lg border border-bar-line px-3 text-[13px]" @click="hideSelected">
              {{ library.segment === 'hidden' ? 'Show' : 'Hide' }}
            </button>
            <button type="button" class="btn h-9 rounded-lg px-2.5 text-[13px] text-rail-muted" @click="library.clearSelection()">Clear</button>
          </div>
        </div>
        <p v-if="notice" class="-mt-3 text-sm text-ink-soft" role="status">{{ notice }}</p>

        <!-- Books -->
        <p v-if="library.error" class="rounded-xl bg-warn-soft p-4 text-sm text-warn-deep">Couldn't load the library: {{ library.error }}</p>
        <p v-else-if="library.loading && library.books.length === 0" class="py-10 text-center text-sm text-ink-soft">Loading…</p>
        <div v-else-if="library.visibleBooks.length === 0" class="py-10 text-center text-sm text-ink-soft">
          <template v-if="library.books.length === 0 && !library.searchQuery">
            <p class="font-semibold text-ink">No books yet</p>
            <p class="mt-1">Add an Audible account under <RouterLink to="/accounts" class="underline">Accounts</RouterLink>, then scan your library.</p>
          </template>
          <p v-else-if="library.searchQuery">No books match “{{ library.searchQuery }}”.</p>
          <p v-else>No books here.</p>
        </div>

        <ul
          v-else-if="library.view === 'list'"
          aria-label="Books"
          class="card overflow-hidden"
        >
          <BookListRow
            v-for="b in library.visibleBooks"
            :key="b.id"
            :book="b"
            :status="statusFor(b)"
            :checked="library.selected.has(b.id)"
            :open="library.openBookId === b.id"
            :selecting="library.selecting"
            @toggle="library.toggleSelected(b.id)"
            @open="library.openBookId = b.id"
          />
        </ul>

        <section v-else aria-label="Books" class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-[18px] gap-y-6">
          <BookGridCard
            v-for="b in library.visibleBooks"
            :key="b.id"
            :book="b"
            :status="statusFor(b)"
            :checked="library.selected.has(b.id)"
            :open="library.openBookId === b.id"
            :selecting="library.selecting"
            @toggle="library.toggleSelected(b.id)"
            @open="library.openBookId = b.id"
          />
        </section>
      </div>
    </div>

    <BookPanel v-if="library.openBookId !== null" :book-id="library.openBookId" @close="library.openBookId = null" />

    <!-- Confirm before queueing many books: Audible may rate-limit big batches. -->
    <Dialog :open="confirm.open" @update:open="(v) => { if (!v) confirm.open = false }">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Download {{ confirm.books.length }} books?</DialogTitle>
          <DialogDescription>
            They'll be queued and downloaded {{ workers }} at a time. Audible may slow down or refuse
            downloads for a while after many in a row; if that happens, the rest can be retried later.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <button type="button" class="btn-secondary" @click="confirm.open = false">Cancel</button>
          <button type="button" class="btn-primary" @click="confirmDownload">Download {{ confirm.books.length }}</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { ChevronDownIcon, LayoutGridIcon, ListIcon, RefreshCwIcon, SearchIcon } from '@lucide/vue'
import type { Account, BookSummary, LibrarySort } from '@/api/client'
import { api } from '@/api/client'
import BookGridCard from '@/components/library/BookGridCard.vue'
import BookListRow from '@/components/library/BookListRow.vue'
import BookPanel from '@/components/library/BookPanel.vue'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { bookStatus } from '@/lib/bookStatus'
import { regionBadge } from '@/lib/regions'
import { useAccountsStore } from '@/stores/accounts'
import { useDownloadsStore } from '@/stores/downloads'
import { sortOptions, useLibraryStore, type Segment } from '@/stores/library'

const library = useLibraryStore()
const downloads = useDownloadsStore()
const accounts = useAccountsStore()

const query = ref(library.searchQuery)
const notice = ref('')
const workers = ref(3)

const views = [
  { value: 'list' as const, label: 'List view', icon: ListIcon },
  { value: 'grid' as const, label: 'Grid view', icon: LayoutGridIcon },
]

onMounted(async () => {
  library.fetchBooks()
  await accounts.fetchAccounts()
  // A saved account filter for an account that no longer exists would hide everything.
  if (library.accountId !== null && !accounts.accounts.some((a) => a.id === library.accountId)) library.setAccount(null)
  api.settings.get().then((s) => (workers.value = s.download_workers)).catch(() => {})
})

function statusFor(b: BookSummary) {
  return bookStatus(b, downloads.jobFor(b.id))
}

function accountLabel(a: Account) {
  return `${a.account_name || a.email} · ${regionBadge(a.locale)}`
}

const summaryLine = computed(() => {
  const n = library.shelved.length
  const accountCount = library.accountId === null ? accounts.accounts.length : 1
  const done = library.segmentBooks.downloaded.length
  const parts = [`${n} book${n === 1 ? '' : 's'}`]
  if (accountCount > 1) parts[0] += ` across ${accountCount} accounts`
  parts.push(`${done} downloaded`)
  return parts.join(' · ')
})

const segments = computed(() => {
  const list: { value: Segment; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'downloaded', label: 'Downloaded' },
    { value: 'not_downloaded', label: 'Not downloaded' },
    { value: 'in_progress', label: 'In progress' },
  ]
  // Only shown when there's something in them (or they're the current tab).
  if (library.segmentBooks.hidden.length || library.segment === 'hidden') list.push({ value: 'hidden', label: 'Hidden' })
  if (library.segmentBooks.removed.length || library.segment === 'removed') list.push({ value: 'removed', label: 'Removed from Audible' })
  return list
})

const scanLabel = computed(() =>
  scanning.value ? 'Scanning…' : accounts.accounts.length > 1 ? 'Scan all accounts' : 'Scan library',
)

const orderLabel = computed(() =>
  library.order === 'asc' ? 'Ascending — switch to descending' : 'Descending — switch to ascending',
)

let searchTimer: ReturnType<typeof setTimeout> | undefined
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => library.search(query.value.trim()), 250)
}

function onAccount(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  library.setAccount(v === '' ? null : Number(v))
}

// --- scanning
const scanning = ref(false)
const scanMessage = ref('')
const scanFailed = ref(false)
const scanMenuOpen = ref(false)
const scanMenuEl = ref<HTMLElement | null>(null)
onClickOutside(scanMenuEl, () => (scanMenuOpen.value = false))

async function scan(accountId: number | null) {
  scanMenuOpen.value = false
  scanning.value = true
  scanMessage.value = ''
  scanFailed.value = false
  const targets = accountId === null ? accounts.accounts : accounts.accounts.filter((a) => a.id === accountId)
  const failed: string[] = []
  for (const a of targets) {
    try {
      await accounts.scanLibrary(a.id)
    } catch {
      failed.push(accountLabel(a))
    }
  }
  scanning.value = false
  await Promise.all([library.fetchBooks(), accounts.fetchAccounts()])
  scanFailed.value = failed.length > 0
  scanMessage.value = failed.length ? `Couldn't scan ${failed.join(', ')}.` : 'Library up to date.'
  setTimeout(() => { if (!scanFailed.value) scanMessage.value = '' }, 4000)
}

// --- selection and bulk actions
const allVisibleSelected = computed(
  () => library.visibleBooks.length > 0 && library.visibleBooks.every((b) => library.selected.has(b.id)),
)
const someVisibleSelected = computed(() => library.visibleBooks.some((b) => library.selected.has(b.id)))
const selectionDownloadable = computed(() =>
  library.selectedBooks.filter((b) => ['none', 'error'].includes(library.stateOf(b))),
)

const confirm = reactive({ open: false, books: [] as BookSummary[] })

function askDownload(books: BookSummary[]) {
  if (books.length === 0) return
  if (books.length === 1) return queue(books)
  confirm.books = books
  confirm.open = true
}

async function confirmDownload() {
  confirm.open = false
  await queue(confirm.books)
}

async function queue(books: BookSummary[]) {
  try {
    const ids = await downloads.enqueueMany(books.map((b) => ({ id: b.id, title: b.title })))
    flash(`Queued ${ids.length} download${ids.length === 1 ? '' : 's'}.`)
    library.clearSelection()
  } catch (e) {
    flash(`Couldn't queue downloads: ${e instanceof Error ? e.message : e}`)
  }
}

async function downloadPdfs() {
  const books = library.selectedBooks
  try {
    const ids = await downloads.enqueueMany(books.map((b) => ({ id: b.id, title: b.title })), { kind: 'pdf' })
    flash(`Fetching PDFs for ${ids.length} book${ids.length === 1 ? '' : 's'} (books without one will say so in Downloads).`)
    library.clearSelection()
  } catch (e) {
    flash(`Couldn't queue PDFs: ${e instanceof Error ? e.message : e}`)
  }
}

async function hideSelected() {
  const ids = [...library.selected]
  const hide = library.segment !== 'hidden'
  await library.setHidden(ids, hide)
  flash(`${hide ? 'Hid' : 'Restored'} ${ids.length} book${ids.length === 1 ? '' : 's'}.`)
}

let noticeTimer: ReturnType<typeof setTimeout> | undefined
function flash(text: string) {
  notice.value = text
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (notice.value = ''), 5000)
}
</script>
