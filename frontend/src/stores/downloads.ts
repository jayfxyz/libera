import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DownloadJob } from '@/api/client'
import { api } from '@/api/client'

export const useDownloadsStore = defineStore('downloads', () => {
  const jobs = ref<Map<string, DownloadJob>>(new Map())

  function handleProgressEvent(event: DownloadJob) {
    jobs.value.set(event.job_id, event)
  }

  async function enqueue(bookId: number, audibleId: string, accountId: number, format = 'm4b') {
    const { job_id } = await api.downloads.enqueue(bookId, audibleId, accountId, format)
    jobs.value.set(job_id, {
      job_id,
      book_id: bookId,
      status: 'queued',
      percent: 0,
    })
    return job_id
  }

  async function cancel(jobId: string) {
    await api.downloads.cancel(jobId)
    jobs.value.delete(jobId)
  }

  const activeJobs = () =>
    Array.from(jobs.value.values()).filter((j) => j.status !== 'done' && j.status !== 'error')

  return { jobs, handleProgressEvent, enqueue, cancel, activeJobs }
})
