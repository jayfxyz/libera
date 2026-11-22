<template>
  <div class="min-w-0 flex-1 overflow-y-auto">
    <div class="flex max-w-[820px] flex-col gap-[18px] px-4 pt-5 pb-12 md:px-9 md:pt-7">
      <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="page-title">Settings</h1>
          <p class="mt-1 text-sm text-ink-soft">Where downloads go and how they're named.</p>
        </div>
        <div class="flex items-center gap-3">
          <span v-if="saved" class="text-sm font-medium text-ok-ink" role="status">Saved</span>
          <span v-else-if="saveError" class="text-sm text-destructive" role="alert">{{ saveError }}</span>
          <button type="button" class="btn-primary" :disabled="!settings || saving" @click="save">
            {{ saving ? 'Saving…' : 'Save settings' }}
          </button>
        </div>
      </header>

      <section class="card flex flex-col gap-3 p-5 md:p-6" aria-labelledby="s-appearance">
        <h2 id="s-appearance" class="text-base font-semibold">Appearance</h2>
        <div role="radiogroup" aria-labelledby="s-appearance" class="flex self-start overflow-hidden rounded-[10px] border border-line bg-surface">
          <button
            v-for="option in themeOptions"
            :key="option.value"
            type="button"
            role="radio"
            class="flex h-[42px] cursor-pointer items-center gap-2 px-4 text-sm"
            :class="theme === option.value ? 'bg-ink font-semibold text-on-ink' : 'font-medium text-ink'"
            :aria-checked="theme === option.value"
            @click="chooseTheme(option.value)"
          >
            <component :is="option.icon" class="size-4" aria-hidden="true" />{{ option.label }}
          </button>
        </div>
        <span class="text-xs text-ink-soft">Applies straight away and is remembered on this device. System follows your device's light or dark setting.</span>
      </section>

      <template v-if="settings">
        <section class="card flex flex-col gap-5 p-5 md:p-6" aria-labelledby="s-downloads">
          <h2 id="s-downloads" class="text-base font-semibold">Downloads</h2>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Output folder
            <input v-model="settings.output_dir" class="textbox font-mono text-[13px]" placeholder="/audiobooks" />
            <span class="text-xs font-normal text-ink-soft">The folder inside the app's container; with Docker it's the AUDIOBOOKS_DIR you mounted.</span>
          </label>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Default format
            <SelectField v-model="settings.default_format" :options="formatOptions" />
            <span class="text-xs font-normal text-ink-soft">Each book's panel can override this.</span>
          </label>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Downloads at the same time
            <input v-model.number="settings.download_workers" type="number" min="1" max="10" class="textbox w-28" />
            <span class="text-xs font-normal text-ink-soft">Takes effect after the app restarts. Fewer is gentler on Audible's limits.</span>
          </label>
        </section>

        <section class="card flex flex-col gap-5 p-5 md:p-6" aria-labelledby="s-naming">
          <h2 id="s-naming" class="text-base font-semibold">File naming</h2>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Book folder
            <input
              v-model="settings.folder_template"
              class="textbox font-mono text-[13px]"
              placeholder="{author} - {title}"
              @focus="activeTemplate = 'folder_template'"
            />
            <span class="text-xs font-normal text-ink-soft">
              Each book gets its own folder for the audio, chapter files, cover and PDF. Leave empty to save directly in the output folder.
            </span>
          </label>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            File name
            <input
              v-model="settings.filename_template"
              class="textbox font-mono text-[13px]"
              placeholder="{title}"
              @focus="activeTemplate = 'filename_template'"
            />
          </label>
          <div class="flex flex-col gap-1.5">
            <span class="text-xs font-semibold text-ink-soft">Result</span>
            <code class="block rounded-[10px] bg-paper px-3 py-2.5 font-mono text-xs leading-normal break-all">{{ examplePath }}</code>
          </div>
          <div class="flex flex-col gap-2">
            <span class="text-xs font-semibold text-ink-soft">
              Tags · tap to add to the {{ activeTemplate === 'folder_template' ? 'book folder' : 'file name' }}
            </span>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="{ tag, description } in templateTags"
                :key="tag"
                type="button"
                class="inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border border-line bg-surface pr-3 pl-1.5 text-xs hover:bg-paper"
                :title="description"
                @mousedown.prevent
                @click="appendTag(tag)"
              >
                <span class="chip">{{ tag }}</span>{{ description }}
              </button>
            </div>
          </div>
        </section>

        <section class="card flex flex-col gap-4 p-5 md:p-6" aria-labelledby="s-tools">
          <h2 id="s-tools" class="text-base font-semibold">Library tools</h2>
          <div class="flex flex-col gap-2">
            <span class="text-sm font-medium">Export the library</span>
            <div class="flex flex-wrap gap-2">
              <a class="btn-secondary" href="/api/library/export?format=csv" download="library.csv"><DownloadIcon class="size-4" />CSV</a>
              <a class="btn-secondary" href="/api/library/export?format=json" download="library.json"><DownloadIcon class="size-4" />JSON</a>
            </div>
          </div>
          <div class="flex flex-col gap-2 border-t border-line-faint pt-4">
            <span class="text-sm font-medium">Find downloaded files</span>
            <span class="text-xs text-ink-soft">Marks books as downloaded when their audio file is already in the output folder, e.g. after copying books in.</span>
            <div class="flex flex-wrap items-center gap-3">
              <button type="button" class="btn-secondary" :disabled="rescanning" @click="rescan">
                <SearchIcon class="size-4" />{{ rescanning ? 'Looking…' : 'Find files' }}
              </button>
              <span v-if="rescanMessage" class="text-sm text-ink-soft" role="status">{{ rescanMessage }}</span>
            </div>
          </div>
        </section>

        <section class="card flex flex-col gap-1.5 p-5 md:p-6" aria-labelledby="s-about">
          <h2 id="s-about" class="text-base font-semibold">About</h2>
          <p class="text-sm text-ink-soft">Libera: a self-hosted manager for your Audible library.</p>
          <p class="text-sm text-ink-soft">App address: <code class="font-mono text-xs text-ink">{{ settings.app_url }}</code> <span class="text-xs">(set with APP_URL)</span></p>
        </section>
      </template>
      <p v-else-if="loadError" class="rounded-xl bg-warn-soft p-4 text-sm text-warn-deep">Couldn't load settings: {{ loadError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { DownloadIcon, MonitorIcon, MoonIcon, SearchIcon, SunIcon } from '@lucide/vue'
import type { Settings } from '@/api/client'
import { api } from '@/api/client'
import { SelectField, type SelectOption } from '@/components/ui/select'
import { setThemeChoice, themeChoice, type ThemeChoice } from '@/lib/theme'
import { useSettingsStore } from '@/stores/settings'

const themeOptions = [
  { value: 'system', label: 'System', icon: MonitorIcon },
  { value: 'light', label: 'Light', icon: SunIcon },
  { value: 'dark', label: 'Dark', icon: MoonIcon },
] as const
const theme = ref<ThemeChoice>(themeChoice())
function chooseTheme(choice: ThemeChoice) {
  theme.value = choice
  setThemeChoice(choice)
}

const formatOptions: SelectOption<Settings['default_format']>[] = [
  { value: 'm4b', label: 'M4B (original audio, no re-encode)' },
  { value: 'mp3', label: 'MP3 (re-encoded with LAME)' },
]

const settings = ref<Settings | null>(null)
const settingsStore = useSettingsStore()
const saved = ref(false)
const saving = ref(false)
const saveError = ref('')
const loadError = ref('')

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
  try {
    settings.value = await api.settings.get()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  }
})

async function save() {
  if (!settings.value) return
  saving.value = true
  saveError.value = ''
  try {
    const { app_url: _readOnly, ...editable } = settings.value
    await api.settings.update(editable)
    await settingsStore.load() // the book panel's "Default — M4B" follows this
    saved.value = true
    setTimeout(() => (saved.value = false), 2500)
  } catch (e) {
    saveError.value = `Couldn't save: ${e instanceof Error ? e.message : e}`
  } finally {
    saving.value = false
  }
}

const rescanning = ref(false)
const rescanMessage = ref('')
async function rescan() {
  rescanning.value = true
  rescanMessage.value = ''
  try {
    const { matched } = await api.library.rescan()
    rescanMessage.value = matched ? `Found ${matched} more downloaded book${matched === 1 ? '' : 's'}.` : 'No new files found.'
  } catch (e) {
    rescanMessage.value = `Failed: ${e instanceof Error ? e.message : e}`
  } finally {
    rescanning.value = false
  }
}
</script>
