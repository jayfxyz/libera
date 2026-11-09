const BASE = '/api'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${method} ${path} → ${res.status}: ${text}`)
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
  account_id: number
  authors: string[]
  narrators: string[]
  genres: string[]
  last_format: 'm4b' | 'mp3' | null
  length_minutes: number
  date_added: string
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
}

export type JobStatus = 'queued' | 'downloading' | 'decrypting' | 'done' | 'error'
export type JobKind = 'audio' | 'pdf'

export interface DownloadJob {
  job_id: string
  book_id: number
  title?: string
  kind?: JobKind
  format?: 'm4b' | 'mp3'
  status: JobStatus
  percent: number
  message?: string
}

export interface DownloadOptions {
  format?: 'm4b' | 'mp3' // default: Settings
  split_chapters?: boolean
  include_pdf?: boolean // default true
  kind?: JobKind // default audio
}

export interface Settings {
  app_url: string
  output_dir: string
  download_workers: number
  default_format: 'm4b' | 'mp3'
  filename_template: string
  folder_template: string
}

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
      request<{ email: string }>('POST', '/accounts/auth/complete', { state, response_url: responseUrl }),
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
  },

  downloads: {
    enqueue: (bookId: number, options: DownloadOptions = {}) =>
      request<{ job_id: string }>('POST', '/downloads', { book_id: bookId, ...options }),
    enqueueMany: (bookIds: number[], options: DownloadOptions = {}) =>
      request<{ jobs: { job_id: string; book_id: number }[] }>('POST', '/downloads/bulk', { book_ids: bookIds, ...options }),
    list: () => request<DownloadJob[]>('GET', '/downloads'),
    cancel: (id: string) => request<void>('DELETE', `/downloads/${id}`),
  },

  settings: {
    get: () => request<Settings>('GET', '/settings'),
    update: (patch: Partial<Settings>) => request<void>('PATCH', '/settings', patch),
  },
}
