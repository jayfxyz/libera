import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Download, DownloadOptions } from '@/api/client'
import { api } from '@/api/client'
import { isActive } from '@/lib/bookStatus'
import { isNewer } from '@/lib/freshness'

export const useDownloadsStore = defineStore('downloads', () => {
  const byId = ref<Map<string, Download>>(new Map())

  /** The server's downloads: on start, and whenever the event stream (re)opens. */
  async function load() {
    for (const download of await api.downloads.list()) upsert(download)
  }

  /** A download from a snapshot or an event; kept unless we already have a newer copy. */
  function upsert(download: Download) {
    const current = byId.value.get(download.id)
    if (!current || isNewer(download.updated_at, current.updated_at)) byId.value.set(download.id, download)
  }

  function remember(id: string, bookId: number, options: DownloadOptions, title?: string) {
    byId.value.set(id, { id, book_id: bookId, title, format: options.format, status: 'queued', percent: 0 })
  }

  async function enqueue(bookId: number, options: DownloadOptions = {}, title?: string) {
    const { id } = await api.downloads.enqueue(bookId, options)
    remember(id, bookId, options, title)
    return id
  }

  async function enqueueMany(books: { id: number; title?: string }[], options: DownloadOptions = {}) {
    if (books.length === 0) return []
    const { downloads: queued } = await api.downloads.enqueueMany(books.map((b) => b.id), options)
    for (const { id, book_id } of queued) {
      remember(id, book_id, options, books.find((b) => b.id === book_id)?.title)
    }
    return queued.map((d) => d.id)
  }

  async function cancel(id: string) {
    await api.downloads.cancel(id)
  }

  /** Run a failed download again (only the decrypt step if its download is still kept). */
  async function retry(id: string) {
    await api.downloads.retry(id)
  }

  /** Run again every book whose latest download failed. */
  async function retryFailed() {
    await api.downloads.retryFailed()
  }

  const active = () => Array.from(byId.value.values()).filter((d) => isActive(d))

  /** Failed downloads that are their book's latest: what retryFailed() runs again. */
  const retryable = () => Array.from(byId.value.values()).filter((d) => d.status === 'failed' && latestFor(d.book_id)?.id === d.id)

  /** The latest download of a book (the most recent one if there were several). */
  function latestFor(bookId: number): Download | undefined {
    let found: Download | undefined
    for (const download of byId.value.values()) {
      if (download.book_id === bookId) found = download
    }
    return found
  }

  return { byId, load, upsert, enqueue, enqueueMany, cancel, retry, retryFailed, active, retryable, latestFor }
})
