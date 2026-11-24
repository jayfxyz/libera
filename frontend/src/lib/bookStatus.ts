import type { BookSummary, Download } from '@/api/client'

/** What a book looks like right now: the library's record plus any live download job. */
export type BookState = 'downloaded' | 'downloading' | 'queued' | 'error' | 'unavailable' | 'none'

export interface BookStatus {
  state: BookState
  label: string
  /** Text and dot colours (Tailwind classes) */
  text: string
  dot: string
  percent: number
}

const ACTIVE = new Set(['queued', 'downloading', 'decrypting'])

export function isActive(job: Download | undefined): job is Download {
  return !!job && ACTIVE.has(job.status)
}

export function bookStatus(
  book: Pick<BookSummary, 'liberation_status' | 'last_format'> & { is_downloadable?: boolean },
  job?: Download,
): BookStatus {
  if (isActive(job)) {
    if (job.status === 'queued') {
      return { state: 'queued', label: 'Queued', text: 'text-ink-soft', dot: 'bg-ink-faint', percent: 0 }
    }
    const phase = job.status === 'decrypting' ? 'Decrypting' : 'Downloading'
    const percent = Math.round(job.percent)
    return {
      state: 'downloading',
      label: job.status === 'decrypting' ? phase : `${phase} · ${percent}%`,
      text: 'text-busy',
      dot: 'bg-busy',
      percent,
    }
  }
  if (book.liberation_status === 'liberated') {
    const fmt = book.last_format ? ` · ${book.last_format.toUpperCase()}` : ''
    return { state: 'downloaded', label: `Downloaded${fmt}`, text: 'text-ok-ink', dot: 'bg-ok', percent: 100 }
  }
  if (book.is_downloadable === false) {
    return { state: 'unavailable', label: 'Not downloadable', text: 'text-ink-soft', dot: 'bg-ink-faint', percent: 0 }
  }
  if (book.liberation_status === 'error') {
    return { state: 'error', label: 'Failed · try again', text: 'text-warn-ink', dot: 'bg-warn', percent: 0 }
  }
  return { state: 'none', label: 'Not downloaded', text: 'text-ink-soft', dot: 'bg-line', percent: 0 }
}

/** "Jane Author · read by Joe Narrator" */
export function byline(book: Pick<BookSummary, 'authors' | 'narrators'>): string {
  const authors = book.authors.join(', ')
  const narrators = book.narrators.join(', ')
  if (narrators && narrators !== authors) return authors ? `${authors} · read by ${narrators}` : `Read by ${narrators}`
  return authors
}

export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

/** "8 Nov 2026" in the browser's locale; "" for missing or placeholder dates. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso || iso.startsWith('1970')) return '' // the import's stand-in when Audible gives no date
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}
