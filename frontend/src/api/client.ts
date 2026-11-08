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

export interface BookSummary {
  id: number
  audible_id: string
  title: string
  cover_url: string
  liberation_status: 'not_liberated' | 'liberated' | 'error' | 'partial_download'
  is_finished: boolean
  is_deleted: boolean
  tags: string
  account_id: number
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
  liberation_status: 'not_liberated' | 'liberated' | 'error' | 'partial_download'
  is_finished: boolean
  tags: string
  user_rating: number | null
  account_id: number
  authors: string[]
  narrators: string[]
  series: { name: string; index: string }[]
}

export interface DownloadJob {
  job_id: string
  book_id: number
  status: 'queued' | 'downloading' | 'decrypting' | 'done' | 'error'
  percent: number
  message?: string
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
    scan: (id: number) => request<void>('POST', `/accounts/${id}/scan`),
  },

  library: {
    list: (params?: { q?: string; page?: number }) => {
      const qs = new URLSearchParams()
      if (params?.q) qs.set('q', params.q)
      if (params?.page) qs.set('page', String(params.page))
      const query = qs.toString() ? `?${qs}` : ''
      return request<BookSummary[]>('GET', `/library${query}`)
    },
    rescan: () => request<{ matched: number }>('POST', '/library/rescan'),
    get: (id: number) => request<BookDetail>('GET', `/library/${id}`),
    update: (id: number, patch: Partial<{ tags: string; user_rating: number; is_finished: boolean }>) =>
      request<void>('PATCH', `/library/${id}`, patch),
  },

  downloads: {
    enqueue: (bookId: number, audibleId: string, accountId: number, format = 'm4b', splitChapters = false) =>
      request<{ job_id: string }>('POST', '/downloads', {
        book_id: bookId,
        audible_id: audibleId,
        account_id: accountId,
        format,
        split_chapters: splitChapters,
      }),
    list: () => request<DownloadJob[]>('GET', '/downloads'),
    cancel: (id: string) => request<void>('DELETE', `/downloads/${id}`),
  },

  settings: {
    get: () => request<Settings>('GET', '/settings'),
    update: (patch: Partial<Settings>) => request<void>('PATCH', '/settings', patch),
  },
}
