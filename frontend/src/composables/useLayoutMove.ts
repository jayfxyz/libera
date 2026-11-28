import { ref, watch, type Ref } from 'vue'
import { api, type MovePreview, type NamingPreset } from '@/api/client'

/** The optional "update my downloaded books to this layout" step: whether it is on, and what it would do.
 *  The preview follows the layout and is fetched only while the step is on. Shared by the welcome dialog and Settings. */
export function useLayoutMove(naming: Ref<NamingPreset>) {
  const enabled = ref(false)
  const preview = ref<MovePreview | null>(null)
  const loading = ref(false)
  const error = ref('')
  let latest = 0 // only the newest answer is shown, however slowly the others arrive

  async function check() {
    const request = ++latest
    loading.value = true
    error.value = ''
    try {
      const answer = await api.library.movePreview(naming.value)
      if (request === latest) preview.value = answer
    } catch (e) {
      if (request === latest) error.value = `Couldn't check your library: ${e instanceof Error ? e.message : e}`
    } finally {
      if (request === latest) loading.value = false
    }
  }

  watch([enabled, naming], () => {
    if (enabled.value) check()
  })

  function reset() {
    latest += 1 // an answer still on its way is no longer wanted
    enabled.value = false
    preview.value = null
    loading.value = false
    error.value = ''
  }

  return { enabled, preview, loading, error, reset }
}
