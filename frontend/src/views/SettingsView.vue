<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="border-b p-6 shrink-0">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-semibold">Settings</h2>
          <p class="text-sm text-muted-foreground">Configure download preferences and output options</p>
        </div>
        <Button @click="save">
          <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
          </svg>
          Save Settings
          <span v-if="saved" class="ml-2 text-green-400 text-xs">✓ Saved</span>
        </Button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto">
      <div v-if="settings" class="p-6 max-w-3xl space-y-6">
        <!-- Download Settings -->
        <Card class="p-6">
          <div class="space-y-6">
            <div>
              <h3 class="text-lg font-semibold flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
                </svg>
                Download Settings
              </h3>
              <p class="text-sm text-muted-foreground">Configure how audiobooks are downloaded and processed</p>
            </div>

            <Separator />

            <div class="space-y-4">
              <div class="space-y-2">
                <Label class="flex items-center gap-2">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                  Output Directory
                </Label>
                <Input v-model="settings.output_dir" placeholder="/path/to/audiobooks" />
                <p class="text-xs text-muted-foreground">Downloaded audiobooks will be saved to this directory</p>
              </div>

              <div class="space-y-2">
                <Label>Default Output Format</Label>
                <Select v-model="settings.default_format">
                  <SelectTrigger class="w-64">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="m4b">M4B (original, no re-encode)</SelectItem>
                    <SelectItem value="mp3">MP3 (re-encode with LAME)</SelectItem>
                  </SelectContent>
                </Select>
                <p class="text-xs text-muted-foreground">Can be overridden per-download in the book detail panel</p>
              </div>

              <div class="space-y-2">
                <Label class="flex items-center gap-2">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                  Concurrent Downloads
                </Label>
                <Input
                  v-model.number="settings.download_workers"
                  type="number"
                  min="1"
                  max="10"
                  class="w-32"
                />
                <p class="text-xs text-muted-foreground">Number of audiobooks that can be downloaded simultaneously</p>
              </div>
            </div>
          </div>
        </Card>

        <!-- File Naming -->
        <Card class="p-6">
          <div class="space-y-6">
            <div>
              <h3 class="text-lg font-semibold">File Naming</h3>
              <p class="text-sm text-muted-foreground">Customize how each book's folder and files are named</p>
            </div>

            <Separator />

            <div class="space-y-4">
              <div class="space-y-2">
                <Label>Book folder</Label>
                <Input
                  v-model="settings.folder_template"
                  placeholder="{author} - {title}"
                  class="font-mono"
                  @focus="activeTemplate = 'folder_template'"
                />
                <p class="text-xs text-muted-foreground">
                  Each book gets its own folder in the output directory, holding the audio, chapter files and PDF.
                  Leave empty to save files directly in the output directory.
                </p>
              </div>

              <div class="space-y-2">
                <Label>File name</Label>
                <Input
                  v-model="settings.filename_template"
                  placeholder="{title}"
                  class="font-mono"
                  @focus="activeTemplate = 'filename_template'"
                />
              </div>

              <p class="text-xs text-muted-foreground">
                Result:
                <span class="font-mono break-all">{{ examplePath }}</span>
              </p>

              <div class="space-y-2">
                <Label>Available Tags</Label>
                <div class="grid grid-cols-2 gap-2">
                  <div
                    v-for="{ tag, description } in templateTags"
                    :key="tag"
                    class="flex items-start gap-2 p-2 rounded bg-muted/50 cursor-pointer hover:bg-muted transition-colors text-sm"
                    @click="appendTag(tag)"
                  >
                    <code class="text-xs font-mono bg-background px-1.5 py-0.5 rounded border shrink-0">{{ tag }}</code>
                    <span class="text-xs text-muted-foreground">{{ description }}</span>
                  </div>
                </div>
                <p class="text-xs text-muted-foreground">
                  Click a tag to append it to the {{ activeTemplate === 'folder_template' ? 'book folder' : 'file name' }} template
                </p>
              </div>
            </div>
          </div>
        </Card>

        <!-- Application -->
        <Card class="p-6">
          <div class="space-y-6">
            <div>
              <h3 class="text-lg font-semibold">Application</h3>
              <p class="text-sm text-muted-foreground">General application settings</p>
            </div>

            <Separator />

            <div class="space-y-2">
              <Label>Application URL</Label>
              <Input v-model="settings.app_url" placeholder="http://localhost:3000" />
              <p class="text-xs text-muted-foreground">Used for OAuth callbacks during Audible authentication</p>
            </div>
          </div>
        </Card>

        <!-- About -->
        <Card class="p-6 bg-muted/30">
          <h4 class="font-semibold mb-2">About Libation Web</h4>
          <div class="text-sm text-muted-foreground space-y-1">
            <p>Version 1.0.0</p>
            <p>A web-based audiobook library manager for Audible</p>
          </div>
        </Card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { Settings } from '@/api/client'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const settings = ref<Settings | null>(null)
const saved = ref(false)

const templateTags = [
  { tag: '{title}', description: 'Book title' },
  { tag: '{author}', description: 'Primary author' },
  { tag: '{narrator}', description: 'Primary narrator' },
  { tag: '{series}', description: 'Series name' },
  { tag: '{series_index}', description: 'Position in series' },
  { tag: '{year}', description: 'Publication year' },
  { tag: '{language}', description: 'Language code' },
  { tag: '{duration_h}', description: 'Duration in hours' },
]

// Which template the tag buttons append to: the last one focused.
const activeTemplate = ref<'folder_template' | 'filename_template'>('folder_template')

function appendTag(tag: string) {
  if (!settings.value) return
  const current = settings.value[activeTemplate.value]
  settings.value[activeTemplate.value] = current ? `${current} ${tag}` : tag
}

// Preview using the same sample book as the placeholder text.
const sample: Record<string, string> = {
  '{title}': 'The Name of the Wind',
  '{author}': 'Patrick Rothfuss',
  '{narrator}': 'Nick Podehl',
  '{series}': 'The Kingkiller Chronicle',
  '{series_index}': '1',
  '{year}': '2007',
  '{language}': 'english',
  '{duration_h}': '27',
}

function render(tmpl: string) {
  return tmpl.replace(/\{[a-z_]+\}/g, (t) => sample[t] ?? t).trim()
}

const examplePath = computed(() => {
  if (!settings.value) return ''
  const s = settings.value
  const file = `${render(s.filename_template) || sample['{title}']}.${s.default_format}`
  const folder = render(s.folder_template)
  return [s.output_dir, folder, file].filter(Boolean).join('/').replace(/\/{2,}/g, '/')
})

onMounted(async () => {
  settings.value = await api.settings.get()
})

async function save() {
  if (!settings.value) return
  await api.settings.update(settings.value)
  saved.value = true
  setTimeout(() => (saved.value = false), 2000)
}
</script>
