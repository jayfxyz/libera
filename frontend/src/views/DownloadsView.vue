<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold mb-6">Downloads</h1>

    <div v-if="jobs.length === 0" class="text-gray-400">No active downloads.</div>

    <ul class="space-y-3">
      <li
        v-for="job in jobs"
        :key="job.job_id"
        class="bg-gray-800 rounded-lg px-4 py-3"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">Book #{{ job.book_id }}</span>
          <span class="text-xs px-2 py-0.5 rounded-full" :class="statusClass(job.status)">
            {{ job.status }}
          </span>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-1.5">
          <div
            class="h-1.5 rounded-full transition-all"
            :class="job.status === 'error' ? 'bg-red-500' : 'bg-indigo-500'"
            :style="{ width: `${job.percent}%` }"
          />
        </div>
        <div v-if="job.message" class="text-xs text-gray-400 mt-1">{{ job.message }}</div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'

const store = useDownloadsStore()
const jobs = computed(() => Array.from(store.jobs.values()))

function statusClass(status: string) {
  return {
    queued: 'bg-gray-600 text-gray-200',
    downloading: 'bg-blue-700 text-blue-100',
    decrypting: 'bg-yellow-700 text-yellow-100',
    done: 'bg-green-700 text-green-100',
    error: 'bg-red-700 text-red-100',
  }[status] ?? 'bg-gray-600 text-gray-200'
}
</script>
