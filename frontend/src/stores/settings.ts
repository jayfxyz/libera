import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type NamingPreset } from '@/api/client'

export const useSettingsStore = defineStore('settings', () => {
  const defaultFormat = ref<'m4b' | 'mp3'>('m4b')
  const naming = ref<NamingPreset>('author_folder')
  // The "Library structure matters" dialog: pending until answered once, reopenable from Settings.
  const layoutDialogPending = ref(false)
  const layoutDialogOpen = ref(false)

  async function load() {
    const s = await api.settings.get()
    defaultFormat.value = s.default_format ?? 'm4b'
    naming.value = s.naming
    layoutDialogPending.value = s.layout_dialog_pending
    if (s.layout_dialog_pending) layoutDialogOpen.value = true
  }

  function openLayoutDialog() {
    layoutDialogOpen.value = true
  }

  /** Closing the dialog answers it, with a new layout or without one ("Not now"). */
  async function answerLayoutDialog(newNaming?: NamingPreset) {
    await api.settings.update({ ...(newNaming ? { naming: newNaming } : {}), layout_dialog_seen: true })
    layoutDialogOpen.value = false
    await load()
  }

  return { defaultFormat, naming, layoutDialogPending, layoutDialogOpen, load, openLayoutDialog, answerLayoutDialog }
})
