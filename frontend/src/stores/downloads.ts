import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DownloadJob, DownloadOptions } from '@/api/client'
import { api } from '@/api/client'
import { isActive } from '@/lib/bookStatus'

export const useDownloadsStore = defineStore('downloads', () => {
  const jobs = ref<Map<string, DownloadJob>>(new Map())

  /** Jobs the server already has (e.g. after a page reload). */
  async function load() {
    for (const job of await api.downloads.list()) jobs.value.set(job.job_id, job)
  }

  function handleProgressEvent(event: DownloadJob) {
    jobs.value.set(event.job_id, { ...jobs.value.get(event.job_id), ...event })
  }

  function remember(jobId: string, bookId: number, options: DownloadOptions, title?: string) {
    jobs.value.set(jobId, { job_id: jobId, book_id: bookId, title, kind: options.kind ?? 'audio', status: 'queued', percent: 0 })
  }

  async function enqueue(bookId: number, options: DownloadOptions = {}, title?: string) {
    const { job_id } = await api.downloads.enqueue(bookId, options)
    remember(job_id, bookId, options, title)
    return job_id
  }

  async function enqueueMany(books: { id: number; title?: string }[], options: DownloadOptions = {}) {
    if (books.length === 0) return []
    const { jobs: queued } = await api.downloads.enqueueMany(books.map((b) => b.id), options)
    for (const { job_id, book_id } of queued) {
      remember(job_id, book_id, options, books.find((b) => b.id === book_id)?.title)
    }
    return queued.map((j) => j.job_id)
  }

  async function cancel(jobId: string) {
    await api.downloads.cancel(jobId)
  }

  const activeJobs = () => Array.from(jobs.value.values()).filter((j) => isActive(j))

  /** The latest audiobook job for a book (the most recent one if there were several). */
  function jobFor(bookId: number): DownloadJob | undefined {
    let found: DownloadJob | undefined
    for (const job of jobs.value.values()) {
      if (job.book_id === bookId && (job.kind ?? 'audio') === 'audio') found = job
    }
    return found
  }

  return { jobs, load, handleProgressEvent, enqueue, enqueueMany, cancel, activeJobs, jobFor }
})
