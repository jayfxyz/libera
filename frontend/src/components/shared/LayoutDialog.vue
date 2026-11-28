<template>
  <Dialog :open="settings.layoutDialogOpen" @update:open="onOpenChange">
    <DialogContent class="max-h-[92dvh] overflow-y-auto sm:max-w-4xl" @open-auto-focus="focusSelectedLayout" @interact-outside="onInteractOutside">
      <DialogHeader>
        <p v-if="!result && !upgrading" class="font-mono text-[11px] font-medium tracking-wider text-brand uppercase">Settings</p>
        <p v-if="upgrading && !result" class="mb-1 text-sm text-ink-soft">
          <span class="mr-1 rounded-full bg-brand/10 px-2 py-0.5 align-[1px] font-mono text-[10px] font-semibold tracking-wider text-brand uppercase">New</span>
          Every book's folder and file name now ends in its audiobook ID (ASIN), like
          <span class="font-mono text-xs">Title [B002UZMLXM]</span>.
          <AsinWhyPopover />
        </p>
        <DialogTitle class="text-2xl">{{ result ? 'Library updated' : 'Library structure matters' }}</DialogTitle>
        <DialogDescription v-if="result" class="sr-only">Your layout was saved and your books were moved.</DialogDescription>
        <DialogDescription v-else>
          Media players and servers find your books by their folders and file names. Pick a layout they all read,
          and Libera will name every new download that way.
          <a :href="DOCS_URL" target="_blank" rel="noopener" class="text-brand underline underline-offset-2">See more details</a>
        </DialogDescription>
      </DialogHeader>

      <LayoutPicker v-if="!result" v-model="selected" />

      <template v-if="result">
        <LayoutMoveResult :result="result" :layout-name="layoutName" />
        <DialogFooter>
          <button type="button" class="btn-primary" @click="settings.closeLayoutDialog()">Done</button>
        </DialogFooter>
      </template>
      <template v-else>
        <div class="border-t border-line pt-4">
          <LayoutMoveOption v-model="moveBooks" :preview="preview" :loading="previewLoading" :error="previewError" :disabled="saving" />
        </div>

        <DialogFooter class="sticky -bottom-4 z-10 items-center bg-paper">
          <span v-if="upgrading" class="text-xs text-ink-soft sm:mr-auto">You can change this later in Settings.</span>
          <button type="button" class="btn-secondary" :disabled="saving" @click="settings.answerLayoutDialog()">{{ upgrading ? 'Not now' : 'Cancel' }}</button>
          <button type="button" class="btn-primary" :disabled="saving || (moveBooks && previewLoading)" @click="save">{{ saveLabel }}</button>
        </DialogFooter>
        <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
      </template>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, type MoveResult, type NamingPreset } from '@/api/client'
import AsinWhyPopover from '@/components/shared/AsinWhyPopover.vue'
import LayoutMoveOption from '@/components/shared/LayoutMoveOption.vue'
import LayoutMoveResult from '@/components/shared/LayoutMoveResult.vue'
import LayoutPicker from '@/components/shared/LayoutPicker.vue'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useLayoutMove } from '@/composables/useLayoutMove'
import { RECOMMENDED_LAYOUT, bookCount, layoutById } from '@/lib/layouts'
import { useSettingsStore } from '@/stores/settings'

const DOCS_URL = 'https://github.com/jayfxyz/libera/blob/main/docs/library-structure.md'

const settings = useSettingsStore()
const selected = ref<NamingPreset>(RECOMMENDED_LAYOUT)
const saving = ref(false)
const error = ref('')
const upgrading = ref(false) // opened for the first time after an upgrade
const result = ref<MoveResult | null>(null)
const { enabled: moveBooks, preview, loading: previewLoading, error: previewError, reset: resetMove } = useLayoutMove(selected)

const layoutName = computed(() => layoutById(selected.value).name)
const saveLabel = computed(() => {
  if (saving.value) return moveBooks.value ? 'Moving…' : 'Saving…'
  if (moveBooks.value && preview.value?.to_move) return `Save and move ${bookCount(preview.value.to_move)}`
  return 'Save layout'
})

// Start on the layout in use, so saving without a change never switches it.
watch(
  () => settings.layoutDialogOpen,
  (open) => {
    if (!open) return
    upgrading.value = settings.layoutDialogPending
    selected.value = settings.naming
    resetMove()
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

// Onboarding asks for a deliberate answer, so a stray click outside must not dismiss it. Opened from
// Settings it is an ordinary dialog, and once the move has run there is nothing left to answer.
function onInteractOutside(event: Event) {
  if (upgrading.value && !result.value) event.preventDefault()
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
