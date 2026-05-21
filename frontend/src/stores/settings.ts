import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'

export const useSettingsStore = defineStore('settings', () => {
  const defaultFormat = ref<'m4b' | 'mp3'>('m4b')

  async function load() {
    const s = await api.settings.get()
    defaultFormat.value = s.default_format ?? 'm4b'
  }

  return { defaultFormat, load }
})
