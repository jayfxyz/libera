<template>
  <Dialog :open="settings.layoutDialogOpen" @update:open="onOpenChange">
    <DialogContent class="max-h-[92dvh] overflow-y-auto sm:max-w-4xl" @open-auto-focus="focusSelectedLayout" @interact-outside.prevent>
      <DialogHeader>
        <p class="font-mono text-[11px] font-medium tracking-wider text-brand uppercase">
          {{ upgrading ? 'New in this version' : 'Settings' }}
        </p>
        <DialogTitle class="text-2xl">Library structure matters</DialogTitle>
        <DialogDescription>
          Media players and servers find your books by their folders and file names. Pick a layout they all read,
          and Libera will name every new download that way.
          <a :href="DOCS_URL" target="_blank" rel="noopener" class="text-brand underline underline-offset-2">Why these layouts?</a>
        </DialogDescription>
      </DialogHeader>

      <div v-if="!result" class="grid min-w-0 gap-6 py-1 md:grid-cols-2">
        <div class="flex min-w-0 flex-col gap-2">
          <h3 class="font-mono text-[11px] font-semibold tracking-wider text-ink-soft uppercase">Choose a layout</h3>
          <div role="radiogroup" aria-label="Folder layout" class="flex flex-col gap-2">
            <LayoutOption v-for="layout in mainLayouts" :key="layout.id" :layout="layout" :selected="selected" @pick="selected = $event" />
            <details class="group" :open="otherLayouts.some((layout) => layout.id === selected)">
              <summary class="flex cursor-pointer list-none items-center gap-1.5 rounded-md px-0.5 py-1.5 text-sm font-semibold text-ink-soft hover:text-ink">
                <ChevronRightIcon class="size-4 transition-transform group-open:rotate-90" aria-hidden="true" />Other options
              </summary>
              <div class="mt-1 flex flex-col gap-2">
                <LayoutOption v-for="layout in otherLayouts" :key="layout.id" :layout="layout" :selected="selected" @pick="selected = $event" />
              </div>
            </details>
          </div>
        </div>

        <div class="flex min-w-0 flex-col gap-2">
          <h3 class="font-mono text-[11px] font-semibold tracking-wider text-ink-soft uppercase">Your library would look like</h3>
          <div class="min-w-0 rounded-[10px] border border-line bg-paper p-4">
            <div class="mb-2 flex justify-between gap-2 font-mono text-[10px] text-ink-soft">
              <span>/audiobooks</span><span>example books</span>
            </div>
            <LayoutTree :nodes="tree" />
            <p class="mt-3 text-xs text-ink-soft">{{ caption }} A colon in a title becomes “ - ” so every system accepts it.</p>
          </div>
        </div>
      </div>

      <template v-if="result">
        <div class="flex flex-col gap-2 border-t border-line pt-4 text-sm" role="status">
          <p class="font-semibold">Moved {{ result.moved }} {{ result.moved === 1 ? 'book' : 'books' }}.</p>
          <p v-if="result.skipped_total" class="text-ink-soft">
            {{ result.skipped_total }} {{ result.skipped_total === 1 ? 'book was' : 'books were' }} left where
            {{ result.skipped_total === 1 ? 'it is' : 'they are' }}: {{ result.skipped.map((b) => `${b.title} (${b.reason.toLowerCase()})`).join('; ') }}.
          </p>
        </div>
        <DialogFooter>
          <button type="button" class="btn-primary" @click="settings.closeLayoutDialog()">Done</button>
        </DialogFooter>
      </template>
      <template v-else>
        <div class="flex flex-col gap-3 border-t border-line pt-4">
          <label class="flex items-start gap-2.5 text-sm">
            <input v-model="moveBooks" type="checkbox" class="mt-0.5 size-4 accent-brand" :disabled="saving" />
            <span>
              <span class="font-semibold">Update previously downloaded books to this layout</span>
              <span class="block text-xs text-ink-soft">
                {{ moveBooks ? 'Libera moves each book folder and remembers the new location.' : 'Off: only new downloads use the layout, and your existing files stay where they are.' }}
              </span>
            </span>
          </label>
          <div v-if="moveBooks" class="pl-6.5">
            <LayoutMovePreview :preview="preview" :loading="previewLoading" :error="previewError" />
          </div>
        </div>

        <DialogFooter class="sticky -bottom-4 z-10 items-center bg-paper">
          <span class="text-xs text-ink-soft sm:mr-auto">You can change this later in Settings.</span>
          <button type="button" class="btn-secondary" :disabled="saving" @click="settings.answerLayoutDialog()">Not now</button>
          <button type="button" class="btn-primary" :disabled="saving || (moveBooks && previewLoading)" @click="save">{{ saveLabel }}</button>
        </DialogFooter>
        <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
      </template>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRightIcon } from '@lucide/vue'
import { api, type MovePreview, type MoveResult, type NamingPreset } from '@/api/client'
import LayoutMovePreview from '@/components/shared/LayoutMovePreview.vue'
import LayoutOption from '@/components/shared/LayoutOption.vue'
import LayoutTree from '@/components/shared/LayoutTree.vue'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { LAYOUTS, RECOMMENDED_LAYOUT, layoutById, layoutTree } from '@/lib/layouts'
import { useSettingsStore } from '@/stores/settings'

const DOCS_URL = 'https://github.com/jayfxyz/libera/blob/main/docs/library-structure.md'

const settings = useSettingsStore()
const selected = ref<NamingPreset>(RECOMMENDED_LAYOUT)
const saving = ref(false)
const error = ref('')

const mainLayouts = LAYOUTS.filter((layout) => !layout.other)
const otherLayouts = LAYOUTS.filter((layout) => layout.other)
const tree = computed(() => layoutTree(selected.value))

const CAPTIONS: Record<NamingPreset, string> = {
  title: 'No author folder, so the author comes from the tags inside each file.',
  author_folder: 'Each book sits in its own folder under its author. The ID in brackets keeps same-title books apart.',
  author_folder_year: 'The year sorts an author’s books by publication date.',
  author_series: 'Series books are numbered 01, 02 so they sort in order. Books with no series skip that folder.',
  author_series_year: 'Series books are numbered, then dated. Books with no series skip that folder.',
}
const caption = computed(() => CAPTIONS[layoutById(selected.value).id])

// The optional second step: move books that are already downloaded.
const upgrading = ref(false) // opened for the first time after an upgrade (not reopened from Settings)
const moveBooks = ref(false)
const preview = ref<MovePreview | null>(null)
const previewLoading = ref(false)
const previewError = ref('')
const result = ref<MoveResult | null>(null)
let previewRequest = 0 // only the latest answer is shown, however slowly the others arrive

const saveLabel = computed(() => {
  if (saving.value) return moveBooks.value ? 'Moving…' : 'Saving…'
  if (moveBooks.value && preview.value?.to_move) return `Save and move ${preview.value.to_move} ${preview.value.to_move === 1 ? 'book' : 'books'}`
  return 'Save layout'
})

async function loadPreview() {
  const request = ++previewRequest
  previewLoading.value = true
  previewError.value = ''
  try {
    const answer = await api.library.movePreview(selected.value)
    if (request === previewRequest) preview.value = answer
  } catch (e) {
    if (request === previewRequest) previewError.value = `Couldn't check your library: ${e instanceof Error ? e.message : e}`
  } finally {
    if (request === previewRequest) previewLoading.value = false
  }
}

watch([moveBooks, selected], () => {
  if (moveBooks.value) loadPreview()
})

// Someone upgrading starts on the recommended layout; reopening from Settings starts on their own.
watch(
  () => settings.layoutDialogOpen,
  (open) => {
    if (!open) return
    upgrading.value = settings.layoutDialogPending
    selected.value = upgrading.value ? RECOMMENDED_LAYOUT : settings.naming
    moveBooks.value = false
    preview.value = null
    result.value = null
    error.value = ''
  },
  { immediate: true },
)

// Start on the chosen layout instead of the first link, so the keyboard is already in the list.
function focusSelectedLayout(event: Event) {
  event.preventDefault()
  ;(event.target as HTMLElement).querySelector<HTMLInputElement>('input[name="layout"]:checked')?.focus()
}

function onOpenChange(open: boolean) {
  if (open) return
  if (result.value) settings.closeLayoutDialog()
  else settings.answerLayoutDialog()
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (moveBooks.value) {
      await settings.saveLayout(selected.value)
      result.value = await api.library.moveBooks(selected.value)
    } else {
      await settings.answerLayoutDialog(selected.value)
    }
  } catch (e) {
    error.value = `Couldn't save: ${e instanceof Error ? e.message : e}`
  } finally {
    saving.value = false
  }
}
</script>
