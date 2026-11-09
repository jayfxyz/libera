<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="border-b p-4 md:p-6 shrink-0">
      <h2 class="text-2xl font-semibold">Downloads</h2>
      <p class="text-sm text-muted-foreground">Active and recent download jobs</p>
    </div>

    <div class="flex-1 overflow-y-auto">
      <div class="p-4 md:p-6">
        <div v-if="jobs.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-muted-foreground mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
          </svg>
          <h3 class="font-semibold mb-2">No downloads</h3>
          <p class="text-sm text-muted-foreground">Download queue is empty</p>
        </div>

        <div v-else class="max-w-2xl space-y-3">
          <div
            v-for="job in jobs"
            :key="job.job_id"
            class="p-4 rounded-lg border bg-card"
          >
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full" :class="dotClass(job.status)" />
                <span class="text-sm font-medium">Book #{{ job.book_id }}</span>
              </div>
              <div class="flex items-center gap-2">
                <Badge :variant="job.status === 'error' ? 'destructive' : job.status === 'done' ? 'default' : 'secondary'">
                  {{ statusLabel(job.status) }}
                </Badge>
                <Button
                  v-if="isActive(job.status)"
                  variant="ghost"
                  size="icon"
                  class="h-8 w-8"
                  aria-label="Cancel download"
                  title="Cancel download"
                  @click="store.cancel(job.job_id)"
                >
                  <XIcon class="h-4 w-4" />
                </Button>
              </div>
            </div>
            <Progress :model-value="job.percent" class="h-1.5" />
            <div class="flex justify-between mt-1.5">
              <p v-if="job.message" class="text-xs text-muted-foreground break-words min-w-0">{{ job.message }}</p>
              <span v-else class="text-xs text-muted-foreground">{{ job.percent }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import { XIcon } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'

const store = useDownloadsStore()
const jobs = computed(() => Array.from(store.jobs.values()))

function isActive(status: string): boolean {
  return status === 'queued' || status === 'downloading' || status === 'decrypting'
}

function dotClass(status: string): string {
  return {
    queued: 'bg-muted-foreground',
    downloading: 'bg-blue-500',
    decrypting: 'bg-yellow-500',
    done: 'bg-green-500',
    error: 'bg-destructive',
  }[status] ?? 'bg-muted-foreground'
}

function statusLabel(status: string): string {
  return {
    queued: 'Queued',
    downloading: 'Downloading',
    decrypting: 'Decrypting',
    done: 'Done',
    error: 'Error',
  }[status] ?? status
}
</script>
