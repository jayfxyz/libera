<template>
  <div class="fixed inset-0 z-40" @click.self="emit('close')" />
  <div class="fixed right-0 top-0 h-dvh w-full sm:w-96 sm:border-l bg-background flex flex-col overflow-hidden shadow-xl z-50">
    <!-- Header -->
    <div class="px-4 py-4 border-b flex items-center justify-between shrink-0">
      <h3 class="font-semibold">Book Details</h3>
      <Button variant="ghost" size="icon" @click="emit('close')">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </Button>
    </div>

    <div v-if="loading" class="flex-1 flex items-center justify-center text-muted-foreground">Loading…</div>
    <div v-else-if="error" class="flex-1 flex items-center justify-center text-destructive text-sm p-4">{{ error }}</div>

    <ScrollArea v-else-if="book" class="flex-1 min-h-0">
      <div class="p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] space-y-6">
        <!-- Cover -->
        <div class="aspect-square rounded-lg overflow-hidden bg-muted">
          <img v-if="book.cover_url" :src="book.cover_url" :alt="book.title" class="w-full h-full object-cover" />
          <div v-else class="w-full h-full flex items-center justify-center text-muted-foreground text-5xl">📖</div>
        </div>

        <!-- Title & Authors -->
        <div>
          <h2 class="text-xl font-semibold leading-tight">{{ book.title }}</h2>
          <p v-if="book.subtitle" class="text-sm text-muted-foreground mt-1">{{ book.subtitle }}</p>
          <p v-if="book.authors.length" class="text-sm mt-2">By {{ book.authors.join(', ') }}</p>
          <p v-if="book.narrators.length" class="text-sm text-muted-foreground">Narrated by {{ book.narrators.join(', ') }}</p>
          <p v-if="book.series.length" class="text-sm text-muted-foreground">
            <span v-for="(s, i) in book.series" :key="i">
              {{ s.name }}<span v-if="s.index"> #{{ s.index }}</span><span v-if="i < book.series.length - 1">, </span>
            </span>
          </p>
        </div>

        <Separator />

        <!-- Metadata -->
        <div class="space-y-3">
          <div v-if="book.length_minutes" class="flex items-center gap-2 text-sm">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
            <span>{{ formatDuration(book.length_minutes) }}</span>
          </div>
          <div v-if="book.audible_rating" class="flex items-center gap-2 text-sm">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
            <span>Audible: {{ book.audible_rating.toFixed(1) }}/5</span>
          </div>
          <div v-if="book.publisher" class="flex items-center gap-2 text-sm">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
            </svg>
            <span>{{ book.publisher }}</span>
          </div>
        </div>

        <Separator />

        <!-- User Rating -->
        <div class="space-y-2">
          <Label>Your Rating</Label>
          <div class="flex gap-1">
            <button
              v-for="star in 5"
              :key="star"
              class="focus:outline-none"
              @click="setRating(star)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 transition-colors" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                :fill="star <= (book.user_rating ?? 0) ? 'currentColor' : 'none'"
                :stroke="star <= (book.user_rating ?? 0) ? 'currentColor' : 'currentColor'"
                :class="star <= (book.user_rating ?? 0) ? 'text-yellow-400' : 'text-muted-foreground'">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Finished Toggle -->
        <div class="flex items-center justify-between">
          <Label class="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            Finished
          </Label>
          <Switch :checked="book.is_finished" @update:checked="toggleFinished" />
        </div>

        <Separator />

        <!-- Tags -->
        <div class="space-y-2">
          <Label class="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>
            </svg>
            Tags
          </Label>
          <div class="flex gap-2 flex-wrap">
            <Badge
              v-for="tag in tagList"
              :key="tag"
              variant="secondary"
              class="gap-1"
            >
              {{ tag }}
              <button class="ml-1 hover:text-destructive leading-none" @click="removeTag(tag)">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </Badge>
            <div v-if="addingTag" class="flex gap-1">
              <Input
                ref="tagInputEl"
                v-model="newTag"
                class="h-6 w-24 text-xs"
                placeholder="tag name"
                @keydown.enter.prevent="commitTag"
                @keydown.escape="addingTag = false; newTag = ''"
                @blur="commitTag"
              />
            </div>
            <Badge
              v-else
              variant="outline"
              class="cursor-pointer"
              @click="startAddingTag"
            >+ Add tag</Badge>
          </div>
        </div>

        <Separator />

        <!-- Description -->
        <div v-if="book.description" class="space-y-2">
          <Label>Description</Label>
          <p class="text-sm text-muted-foreground leading-relaxed line-clamp-6">{{ book.description }}</p>
        </div>

        <!-- Download Section -->
        <div v-if="book.liberation_status !== 'liberated'" class="space-y-4">
          <h4 class="font-semibold">Download Options</h4>

          <div class="space-y-2">
            <Label>Output Format</Label>
            <Select v-model="selectedFormat">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="m4b">M4B (Audiobook)</SelectItem>
                <SelectItem value="mp3">MP3</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="flex items-center gap-2">
            <Checkbox id="chapters" v-model:checked="splitChapters" />
            <Label for="chapters" class="cursor-pointer flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="21" y1="6" x2="3" y2="6"/><line x1="15" y1="12" x2="3" y2="12"/><line x1="17" y1="18" x2="3" y2="18"/>
              </svg>
              Split into chapters
            </Label>
          </div>

          <!-- Active download progress -->
          <div v-if="activeJob" class="space-y-1">
            <div class="flex justify-between text-xs text-muted-foreground">
              <span>{{ activeJob.status === 'decrypting' ? 'Decrypting…' : 'Downloading…' }}</span>
              <span>{{ activeJob.percent }}%</span>
            </div>
            <Progress :model-value="activeJob.percent" class="h-1.5" />
          </div>

          <Button class="w-full" size="lg" :disabled="isDownloading" @click="handleDownload">
            <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
            </svg>
            {{ isDownloading ? 'Downloading…' : 'Download & Decrypt' }}
          </Button>
        </div>

        <!-- Downloaded status -->
        <div v-if="book.liberation_status === 'liberated'" class="p-4 bg-green-50 rounded-lg border border-green-200">
          <div class="flex items-center gap-2 text-green-700">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span class="font-medium">Downloaded</span>
          </div>
          <p class="text-sm text-green-600 mt-1">This audiobook has been downloaded and decrypted.</p>
          <Button variant="outline" size="sm" class="mt-3 w-full" :disabled="isDownloading" @click="handleDownload">
            Re-download
          </Button>
        </div>

      </div>
    </ScrollArea>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import type { BookDetail } from '@/api/client'
import { api } from '@/api/client'
import { useDownloadsStore } from '@/stores/downloads'
import { useSettingsStore } from '@/stores/settings'
import { useLibraryStore } from '@/stores/library'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Progress } from '@/components/ui/progress'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const props = defineProps<{ bookId: number }>()
const emit = defineEmits<{ close: [] }>()

const book = ref<BookDetail | null>(null)
const loading = ref(true)
const error = ref('')

const downloadsStore = useDownloadsStore()
const settingsStore = useSettingsStore()
const libraryStore = useLibraryStore()
const selectedFormat = ref<'m4b' | 'mp3'>(settingsStore.defaultFormat)
const splitChapters = ref(false)
const addingTag = ref(false)
const newTag = ref('')
const tagInputEl = ref<HTMLInputElement | null>(null)

onMounted(async () => {
  selectedFormat.value = settingsStore.defaultFormat
  try {
    book.value = await api.library.get(props.bookId)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const activeJob = computed(() =>
  book.value
    ? Array.from(downloadsStore.jobs.values()).find(
        j => j.book_id === book.value!.id && j.status !== 'done' && j.status !== 'error',
      )
    : undefined,
)
const isDownloading = computed(() => !!activeJob.value)

async function handleDownload() {
  if (!book.value) return
  await downloadsStore.enqueue(book.value.id, book.value.audible_id, book.value.account_id, selectedFormat.value, splitChapters.value)
}

async function setRating(star: number) {
  if (!book.value) return
  const user_rating = book.value.user_rating === star ? null : star
  await api.library.update(book.value.id, { user_rating: user_rating ?? undefined })
  book.value.user_rating = user_rating
}

async function toggleFinished() {
  if (!book.value) return
  const is_finished = !book.value.is_finished
  await api.library.update(book.value.id, { is_finished })
  book.value.is_finished = is_finished
  libraryStore.updateBook(book.value.id, { is_finished })
}

const tagList = computed(() =>
  book.value?.tags ? book.value.tags.split(' ').filter(Boolean) : [],
)

function startAddingTag() {
  addingTag.value = true
  newTag.value = ''
  nextTick(() => tagInputEl.value?.focus())
}

async function commitTag() {
  const tag = newTag.value.trim().replace(/\s+/g, '_')
  addingTag.value = false
  newTag.value = ''
  if (!tag || tagList.value.includes(tag)) return
  await saveTags([...tagList.value, tag].join(' '))
}

async function removeTag(tag: string) {
  await saveTags(tagList.value.filter(t => t !== tag).join(' '))
}

async function saveTags(tags: string) {
  if (!book.value) return
  await api.library.update(book.value.id, { tags })
  book.value.tags = tags
  libraryStore.updateBook(book.value.id, { tags })
}

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}
</script>
