<template>
  <div class="w-96 border-l bg-background flex flex-col overflow-hidden shrink-0">
    <!-- Header -->
    <div class="p-4 border-b flex items-center justify-between">
      <div>
        <h3 class="font-semibold">Download Queue</h3>
        <p class="text-xs text-muted-foreground">{{ activeJobs.length }} active, {{ completedJobs.length }} completed</p>
      </div>
      <Button variant="ghost" size="icon" @click="emit('close')">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </Button>
    </div>

    <!-- Job list -->
    <ScrollArea class="flex-1">
      <div class="p-4 space-y-6">
        <!-- Active -->
        <div v-if="activeJobs.length > 0" class="space-y-3">
          <h4 class="text-sm font-semibold text-muted-foreground">Active</h4>
          <div v-for="job in activeJobs" :key="job.job_id" class="p-3 rounded-lg border space-y-2">
            <div class="flex items-start gap-3">
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium">Book #{{ job.book_id }}</p>
                <div class="flex items-center gap-1.5 mt-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-blue-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
                  </svg>
                  <span class="text-xs text-muted-foreground">{{ jobStatusText(job.status) }}</span>
                </div>
              </div>
              <Button variant="ghost" size="icon" class="h-7 w-7 shrink-0" @click="store.cancel(job.job_id)">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
              </Button>
            </div>
            <div class="space-y-1">
              <Progress :model-value="job.percent" class="h-1.5" />
              <p class="text-xs text-muted-foreground">{{ job.percent }}%</p>
            </div>
            <p v-if="job.message" class="text-xs text-muted-foreground">{{ job.message }}</p>
          </div>
        </div>

        <Separator v-if="activeJobs.length > 0 && completedJobs.length > 0" />

        <!-- Completed -->
        <div v-if="completedJobs.length > 0" class="space-y-3">
          <h4 class="text-sm font-semibold text-muted-foreground">Completed</h4>
          <div v-for="job in completedJobs" :key="job.job_id" class="flex items-center gap-3 p-3 rounded-lg border bg-green-50">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-green-600 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium">Book #{{ job.book_id }}</p>
              <p class="text-xs text-green-700">Completed</p>
            </div>
          </div>
        </div>

        <Separator v-if="(activeJobs.length > 0 || completedJobs.length > 0) && failedJobs.length > 0" />

        <!-- Failed -->
        <div v-if="failedJobs.length > 0" class="space-y-3">
          <h4 class="text-sm font-semibold text-muted-foreground">Failed</h4>
          <div v-for="job in failedJobs" :key="job.job_id" class="p-3 rounded-lg border bg-destructive/5 space-y-1.5">
            <div class="flex items-center gap-3">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-destructive shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium">Book #{{ job.book_id }}</p>
                <p class="text-xs text-destructive">Failed</p>
              </div>
            </div>
            <p v-if="job.message" class="text-xs text-destructive/80 bg-destructive/10 p-1.5 rounded">{{ job.message }}</p>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="jobs.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-muted-foreground mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
          </svg>
          <h4 class="font-semibold mb-1">No downloads</h4>
          <p class="text-sm text-muted-foreground">Download queue is empty</p>
        </div>
      </div>
    </ScrollArea>

    <!-- Cancel all footer -->
    <template v-if="activeJobs.length > 0">
      <Separator />
      <div class="p-4">
        <Button variant="outline" class="w-full" size="sm" @click="cancelAll">
          <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          Cancel All
        </Button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'

const emit = defineEmits<{ close: [] }>()
const store = useDownloadsStore()

const jobs = computed(() => Array.from(store.jobs.values()))
const activeJobs = computed(() => jobs.value.filter(j => j.status !== 'done' && j.status !== 'error'))
const completedJobs = computed(() => jobs.value.filter(j => j.status === 'done'))
const failedJobs = computed(() => jobs.value.filter(j => j.status === 'error'))

function jobStatusText(status: string): string {
  return { queued: 'Queued', downloading: 'Downloading…', decrypting: 'Decrypting…' }[status] ?? status
}

function cancelAll() {
  activeJobs.value.forEach(j => store.cancel(j.job_id))
}
</script>
