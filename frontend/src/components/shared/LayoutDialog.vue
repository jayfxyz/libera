<template>
  <Dialog :open="settings.layoutDialogOpen" @update:open="onOpenChange">
    <DialogContent class="max-h-[92dvh] overflow-y-auto sm:max-w-4xl" @open-auto-focus="focusSelectedLayout" @interact-outside.prevent>
      <DialogHeader>
        <p v-if="!result" class="font-mono text-[11px] font-medium tracking-wider text-brand uppercase">
          {{ upgrading ? 'New in this version' : 'Settings' }}
        </p>
        <DialogTitle class="text-2xl">{{ result ? 'Library updated' : 'Library structure matters' }}</DialogTitle>
        <DialogDescription v-if="result" class="sr-only">Your layout was saved and your books were moved.</DialogDescription>
        <DialogDescription v-else>
          Media players and servers find your books by their folders and file names. Pick a layout they all read,
          and Libera will name every new download that way.
          <a :href="DOCS_URL" target="_blank" rel="noopener" class="text-brand underline underline-offset-2">Why these layouts?</a>
        </DialogDescription>
      </DialogHeader>

      <LayoutPicker v-if="!result" v-model="selected" />

      <template v-if="result">
        <div class="flex flex-col gap-4 text-sm" role="status">
          <div class="flex flex-col gap-1">
            <p class="flex items-center gap-2 text-base font-semibold">
              <CircleCheckIcon class="size-5 shrink-0 text-ok" aria-hidden="true" />{{ movedHeadline }}
            </p>
            <p v-if="result.to_rename" class="pl-7 text-ink-soft">
              {{ plural(result.to_rename) }} also had {{ result.to_rename === 1 ? 'its' : 'their' }} files renamed to include the book's ID.
            </p>
            <p class="pl-7 text-ink-soft">New downloads use {{ layoutName }} too.</p>
          </div>
          <div v-if="result.skipped_total" class="flex flex-col gap-2 rounded-[10px] border border-line bg-paper p-4">
            <p class="font-semibold">Left where {{ result.skipped_total === 1 ? 'it is' : 'they are' }} ({{ result.skipped_total }})</p>
            <ul class="flex flex-col gap-1 text-xs">
              <li v-for="book in result.skipped" :key="book.book_id" class="flex flex-wrap gap-x-2">
                <span class="font-medium">{{ book.title || 'Untitled' }}</span>
                <span class="text-ink-soft">{{ book.reason }}</span>
              </li>
              <li v-if="result.skipped_total > result.skipped.length" class="text-ink-soft">
                and {{ result.skipped_total - result.skipped.length }} more
              </li>
            </ul>
          </div>
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
import { CircleCheckIcon } from '@lucide/vue'
import { api, type MovePreview, type MoveResult, type NamingPreset } from '@/api/client'
import LayoutMovePreview from '@/components/shared/LayoutMovePreview.vue'
import LayoutPicker from '@/components/shared/LayoutPicker.vue'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RECOMMENDED_LAYOUT, layoutById } from '@/lib/layouts'
import { useSettingsStore } from '@/stores/settings'

const DOCS_URL = 'https://github.com/jayfxyz/libera/blob/main/docs/library-structure.md'

const settings = useSettingsStore()
const selected = ref<NamingPreset>(RECOMMENDED_LAYOUT)
const saving = ref(false)
const error = ref('')

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

function plural(count: number): string {
  return `${count} ${count === 1 ? 'book' : 'books'}`
}

const layoutName = computed(() => layoutById(selected.value).name)
const movedHeadline = computed(() =>
  !result.value || result.value.moved === 0
    ? 'No books needed moving.'
    : `Moved ${plural(result.value.moved)} to ${layoutName.value}.`,
)

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
  ;(event.target as HTMLElement).querySelector<HTMLInputElement>('input[type="radio"]:checked')?.focus()
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
