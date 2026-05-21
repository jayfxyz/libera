<template>
  <div class="p-6 max-w-lg">
    <h1 class="text-2xl font-bold mb-6">Settings</h1>

    <div v-if="settings" class="space-y-5">
      <div>
        <label class="block text-sm text-gray-400 mb-1">App URL</label>
        <input
          v-model="settings.app_url"
          type="text"
          class="w-full px-3 py-2 bg-gray-800 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <p class="text-xs text-gray-500 mt-1">Used to construct the Audible OAuth redirect URI.</p>
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Output Directory</label>
        <input
          v-model="settings.output_dir"
          type="text"
          class="w-full px-3 py-2 bg-gray-800 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Default Output Format</label>
        <select
          v-model="settings.default_format"
          class="w-48 px-3 py-2 bg-gray-800 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="m4b">M4B (original, no re-encode)</option>
          <option value="mp3">MP3 (re-encode with LAME)</option>
        </select>
        <p class="text-xs text-gray-500 mt-1">Can be overridden per download.</p>
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Filename Template</label>
        <input
          v-model="settings.filename_template"
          type="text"
          class="w-full px-3 py-2 bg-gray-800 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="{title}"
        />
        <p class="text-xs text-gray-500 mt-1">
          Tags: <code class="text-gray-400">{title} {author} {narrator} {series} {series_index} {year} {language} {duration_h}</code>
        </p>
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Download Workers</label>
        <input
          v-model.number="settings.download_workers"
          type="number"
          min="1"
          max="10"
          class="w-32 px-3 py-2 bg-gray-800 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <button
        @click="save"
        class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium"
      >
        Save
      </button>

      <p v-if="saved" class="text-sm text-green-400">Settings saved.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { Settings } from '@/api/client'
import { api } from '@/api/client'

const settings = ref<Settings | null>(null)
const saved = ref(false)

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
