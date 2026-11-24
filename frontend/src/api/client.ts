const BASE = '/api'

/** A failed API call; `status` is the HTTP status. */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(`${method} ${path} → ${res.status}: ${text}`, res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// --- Types ---

export interface Account {
  id: number
  account_name: string
  email: string
  locale: string
  library_scan_enabled: boolean
  last_scanned_at: string | null
}

export type LibrarySort = 'title' | 'author' | 'added' | 'released' | 'length' | 'series' | 'rating' | 'downloaded'
export type SortOrder = 'asc' | 'desc'

export type LiberationStatus = 'not_liberated' | 'liberated' | 'error' | 'partial_download'

export interface BookSummary {
  id: number
  audible_id: string
  title: string
  cover_url: string
  liberation_status: LiberationStatus
  is_finished: boolean
  is_deleted: boolean
  is_hidden: boolean
  tags: string
  account_id: number // the library entry this row shows
  account_ids: number[] // every account that owns the book (one row per book across accounts)
  authors: string[]
  narrators: string[]
  genres: string[]
  last_format: 'm4b' | 'mp3' | null
  length_minutes: number
  date_added: string
  has_pdf: boolean | null // a companion PDF exists; null until the next library sync
  updated_at: string | null // ISO UTC; which copy is newer when a snapshot and an event cross
}

export interface BookDetail {
  id: number
  audible_id: string
  title: string
  subtitle: string
  description: string
  cover_url: string
  length_minutes: number
  publisher: string
  language: string
  audible_rating: number
  liberation_status: LiberationStatus
  is_finished: boolean
  is_hidden: boolean
  tags: string
  user_rating: number | null
  account_id: number
  authors: string[]
  narrators: string[]
  genres: string[]
  series: { name: string; index: string }[]
  last_format: 'm4b' | 'mp3' | null
  file_path: string | null // where the last download was saved
  planned_path: string // where a download would go with the current settings
  has_pdf: boolean | null // a companion PDF exists; null until the next library sync
  updated_at: string | null // ISO UTC; which copy is newer when a snapshot and an event cross
}

export type JobStatus = 'queued' | 'downloading' | 'decrypting' | 'done' | 'failed' | 'cancelled'

/** A file a finished download wrote, within the book's folder. */
export interface DownloadFile {
  role: 'audio' | 'chapter' | 'pdf' | 'cover' | 'metadata'
  name: string
  size_bytes: number
}

export interface Download {
  id: string
  book_id: number
  title?: string
  format?: 'm4b' | 'mp3'
  status: JobStatus
  percent: number
  message?: string // failed: why; done: the audio file's path; queued: why it is retrying
  retry_at?: string // ISO UTC: a waiting download's next try (e.g. Audible is throttling the account)
  created_at?: string // ISO UTC
  finished_at?: string | null
  files?: DownloadFile[] | null // what a finished download wrote (null for older downloads)
  updated_at?: string // ISO UTC; which copy is newer when a snapshot and an event cross
}

export interface DownloadOptions {
  format?: 'm4b' | 'mp3' // default: Settings
  split_chapters?: boolean
}

export interface Settings {
  output_dir: string // read-only: set by OUTPUT_DIR (the Docker mount)
  download_workers: number
  default_format: 'm4b' | 'mp3'
  naming: NamingPreset
}

/** Where a book's files go in the output folder; the audio file is always named after the title. */
export type NamingPreset = 'author_title' | 'author_folder' | 'author_folder_year' | 'author_series' | 'author_series_year'

// --- Accounts ---

export const api = {
  accounts: {
    list: () => request<Account[]>('GET', '/accounts'),
    update: (id: number, patch: { account_name?: string }) =>
      request<void>('PATCH', `/accounts/${id}`, patch),
    delete: (id: number) => request<void>('DELETE', `/accounts/${id}`),
    authStart: (locale: string, name: string) =>
      request<{ auth_url: string; state: string }>('POST', '/accounts/auth/start', { locale, name }),
    authComplete: (state: string, responseUrl: string) =>
      request<{ id: number; email: string }>('POST', '/accounts/auth/complete', { state, response_url: responseUrl }),
    scan: (id: number) => request<{ imported: number }>('POST', `/accounts/${id}/scan`),
  },

  library: {
    list: (params?: {
      q?: string
      page?: number
      limit?: number
      sort?: LibrarySort
      order?: SortOrder
      accountId?: number | null
    }) => {
      const qs = new URLSearchParams()
      if (params?.q) qs.set('q', params.q)
      if (params?.page) qs.set('page', String(params.page))
      if (params?.limit) qs.set('limit', String(params.limit))
      if (params?.accountId != null) qs.set('account_id', String(params.accountId))
      if (params?.sort) qs.set('sort', params.sort)
      if (params?.order) qs.set('order', params.order)
      const query = qs.toString() ? `?${qs}` : ''
      return request<BookSummary[]>('GET', `/library${query}`)
    },
    rescan: () => request<{ matched: number }>('POST', '/library/rescan'),
    get: (id: number) => request<BookDetail>('GET', `/library/${id}`),
    update: (id: number, patch: Partial<{ tags: string; user_rating: number | null; is_finished: boolean; is_hidden: boolean }>) =>
      request<void>('PATCH', `/library/${id}`, patch),
    setHidden: (bookIds: number[], isHidden: boolean) =>
      request<void>('POST', '/library/bulk', { book_ids: bookIds, is_hidden: isHidden }),
    savePdf: (id: number) => request<{ file_path: string }>('POST', `/library/${id}/pdf`),
  },

  downloads: {
    enqueue: (bookId: number, options: DownloadOptions = {}) =>
      request<{ id: string }>('POST', '/downloads', { book_id: bookId, ...options }),
    enqueueMany: (bookIds: number[], options: DownloadOptions = {}) =>
      request<{ downloads: { id: string; book_id: number }[] }>('POST', '/downloads/bulk', { book_ids: bookIds, ...options }),
    list: () => request<Download[]>('GET', '/downloads'),
    cancel: (id: string) => request<void>('DELETE', `/downloads/${id}`),
    retry: (id: string) => request<{ id: string }>('POST', `/downloads/${id}/retry`),
    retryFailed: () => request<{ downloads: { id: string }[] }>('POST', '/downloads/retry-failed'),
  },

  settings: {
    get: () => request<Settings>('GET', '/settings'),
    update: (patch: Partial<Settings>) => request<void>('PATCH', '/settings', patch),
  },
}
