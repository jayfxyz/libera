import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { BookSummary, LibrarySort, SortOrder } from '@/api/client'
import { api } from '@/api/client'
import { bookStatus } from '@/lib/bookStatus'
import { isNewer } from '@/lib/freshness'
import { useDownloadsStore } from './downloads'

/** Sort options, each with the direction it starts in when picked. */
export const sortOptions: { value: LibrarySort; label: string; defaultOrder: SortOrder }[] = [
  { value: 'added', label: 'Date added', defaultOrder: 'desc' },
  { value: 'title', label: 'Title', defaultOrder: 'asc' },
  { value: 'author', label: 'Author', defaultOrder: 'asc' },
  { value: 'released', label: 'Release date', defaultOrder: 'desc' },
  { value: 'length', label: 'Length', defaultOrder: 'desc' },
  { value: 'series', label: 'Series', defaultOrder: 'asc' },
  { value: 'rating', label: 'Audible rating', defaultOrder: 'desc' },
  { value: 'downloaded', label: 'Recently downloaded', defaultOrder: 'desc' },
]

export type Segment = 'all' | 'downloaded' | 'not_downloaded' | 'in_progress' | 'hidden' | 'removed'
export type ViewMode = 'list' | 'grid'

const PAGE = 500 // the API's largest page; the whole library is loaded so counts and "select all" are exact

/** Per-browser preferences; storage may be unavailable (private mode). */
const PREFS_KEY = 'library.prefs'
interface Prefs { sort: LibrarySort; order: SortOrder; view: ViewMode; accountId: number | null }
function loadPrefs(): Prefs {
  const fallback: Prefs = { sort: 'added', order: 'desc', view: 'list', accountId: null }
  try {
    const saved = { ...JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') }
    // The sort used to be saved on its own.
    const legacy = JSON.parse(localStorage.getItem('library.sort') ?? 'null')
    if (legacy && !saved.sort) Object.assign(saved, legacy)
    return {
      sort: sortOptions.some((o) => o.value === saved.sort) ? saved.sort : fallback.sort,
      order: saved.order === 'asc' || saved.order === 'desc' ? saved.order : fallback.order,
      view: saved.view === 'grid' || saved.view === 'list' ? saved.view : fallback.view,
      accountId: typeof saved.accountId === 'number' ? saved.accountId : null,
    }
  } catch {
    return fallback
  }
}

export const useLibraryStore = defineStore('library', () => {
  const downloads = useDownloadsStore()
  const prefs = loadPrefs()

  const books = ref<BookSummary[]>([])
  const loading = ref(false)
  const error = ref('')
  const searchQuery = ref('')
  const sort = ref<LibrarySort>(prefs.sort)
  const order = ref<SortOrder>(prefs.order)
  const view = ref<ViewMode>(prefs.view)
  const accountId = ref<number | null>(prefs.accountId)
  const segment = ref<Segment>('all')
  const selected = ref<Set<number>>(new Set())
  /** Turned on with the toolbar's Select button (phones have no hover to reveal checkboxes). */
  const selectMode = ref(false)
  /** Every book shows its checkbox while selecting; otherwise only on hover/focus. */
  const selecting = computed(() => selectMode.value || selected.value.size > 0)
  const openBookId = ref<number | null>(null)

  watch([sort, order, view, accountId], () => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({
        sort: sort.value, order: order.value, view: view.value, accountId: accountId.value,
      }))
    } catch {
      /* ignore */
    }
  })

  let requestSeq = 0
  async function fetchBooks() {
    const seq = ++requestSeq
    loading.value = true
    error.value = ''
    try {
      const all: BookSummary[] = []
      for (let page = 1; ; page++) {
        const batch = await api.library.list({
          q: searchQuery.value || undefined, page, limit: PAGE,
          sort: sort.value, order: order.value, accountId: accountId.value,
        })
        all.push(...batch)
        if (batch.length < PAGE) break
      }
      if (seq !== requestSeq) return // a newer search/sort superseded this one
      // An event may have brought a newer copy while this was loading.
      const loaded = new Map(books.value.map((b) => [b.id, b]))
      books.value = all.map((b) => {
        const current = loaded.get(b.id)
        return current && !isNewer(b.updated_at, current.updated_at) ? current : b
      })
      // Keep the selection to books that are still listed.
      const ids = new Set(all.map((b) => b.id))
      selected.value = new Set([...selected.value].filter((id) => ids.has(id)))
    } catch (e: unknown) {
      if (seq === requestSeq) error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  const stateOf = (b: BookSummary) => bookStatus(b, downloads.latestFor(b.id)).state

  // Books that count as "in the library": not removed from Audible, not hidden.
  const shelved = computed(() => books.value.filter((b) => !b.is_deleted && !b.is_hidden))

  const segmentBooks = computed<Record<Segment, BookSummary[]>>(() => ({
    all: shelved.value,
    downloaded: shelved.value.filter((b) => stateOf(b) === 'downloaded'),
    not_downloaded: shelved.value.filter((b) => stateOf(b) !== 'downloaded'),
    in_progress: shelved.value.filter((b) => ['queued', 'downloading'].includes(stateOf(b))),
    hidden: books.value.filter((b) => b.is_hidden && !b.is_deleted),
    removed: books.value.filter((b) => b.is_deleted),
  }))

  const visibleBooks = computed(() => segmentBooks.value[segment.value])

  /** Books "Download all" would queue: in the library and neither downloaded nor in progress. */
  const downloadable = computed(() => shelved.value.filter((b) => ['none', 'error'].includes(stateOf(b))))

  const selectedBooks = computed(() => books.value.filter((b) => selected.value.has(b.id)))

  function toggleSelected(id: number) {
    const next = new Set(selected.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selected.value = next
  }

  function selectAllVisible(on: boolean) {
    const next = new Set(selected.value)
    for (const b of visibleBooks.value) {
      if (on) next.add(b.id)
      else next.delete(b.id)
    }
    selected.value = next
  }

  function clearSelection() {
    selected.value = new Set()
    selectMode.value = false
  }

  function setSort(s: LibrarySort) {
    if (s === sort.value) return
    sort.value = s
    order.value = sortOptions.find((o) => o.value === s)?.defaultOrder ?? 'asc'
    fetchBooks()
  }

  function toggleOrder() {
    order.value = order.value === 'asc' ? 'desc' : 'asc'
    fetchBooks()
  }

  function setAccount(id: number | null) {
    accountId.value = id
    fetchBooks()
  }

  function search(q: string) {
    searchQuery.value = q
    fetchBooks()
  }

  /** Apply a change to books already loaded (after a PATCH or a finished download). */
  function patchBooks(ids: number[], patch: Partial<BookSummary>) {
    const set = new Set(ids)
    books.value = books.value.map((b) => (set.has(b.id) ? { ...b, ...patch } : b))
  }

  /** A book from an event; replaces the loaded copy unless that one is newer.
   *  Books that aren't loaded (another filter or search) are ignored. */
  function upsertBook(book: BookSummary) {
    books.value = books.value.map((b) => (b.id === book.id && isNewer(book.updated_at, b.updated_at) ? book : b))
  }

  async function setHidden(ids: number[], hidden: boolean) {
    await api.library.setHidden(ids, hidden)
    patchBooks(ids, { is_hidden: hidden })
    const next = new Set(selected.value)
    ids.forEach((id) => next.delete(id))
    selected.value = next
  }

  return {
    books, loading, error, searchQuery, sort, order, view, accountId, segment, selected, selectMode, selecting, openBookId,
    segmentBooks, visibleBooks, downloadable, selectedBooks, shelved,
    fetchBooks, toggleSelected, selectAllVisible, clearSelection, setSort, toggleOrder, setAccount, search,
    patchBooks, upsertBook, setHidden, stateOf,
  }
})
