import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import type { MovePreview, NamingPreset } from '@/api/client'
import { api } from '@/api/client'
import { useLayoutMove } from '../useLayoutMove'

const answer = (to_move: number): MovePreview => ({ to_move, to_rename: 0, in_place: 0, skipped_total: 0, skipped: [], examples: [] })

async function settle() {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

describe('useLayoutMove', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('looks at the library only while it is on', async () => {
    const preview = vi.spyOn(api.library, 'movePreview').mockResolvedValue(answer(3))
    const naming = ref<NamingPreset>('author_folder')
    const move = useLayoutMove(naming)
    naming.value = 'title'
    await settle()
    expect(preview).not.toHaveBeenCalled()

    move.enabled.value = true
    await settle()
    expect(preview).toHaveBeenCalledWith('title')
    expect(move.preview.value?.to_move).toBe(3)
  })

  it('looks again when the layout changes', async () => {
    const preview = vi.spyOn(api.library, 'movePreview').mockResolvedValue(answer(1))
    const naming = ref<NamingPreset>('author_folder')
    const move = useLayoutMove(naming)
    move.enabled.value = true
    await settle()
    naming.value = 'author_series'
    await settle()
    expect(preview.mock.calls.map(([layout]) => layout)).toEqual(['author_folder', 'author_series'])
  })

  it('shows only the newest answer, however late an older one arrives', async () => {
    let finishFirst: (value: MovePreview) => void = () => {}
    vi.spyOn(api.library, 'movePreview')
      .mockImplementationOnce(() => new Promise((resolve) => (finishFirst = resolve)))
      .mockResolvedValueOnce(answer(2))
    const naming = ref<NamingPreset>('author_folder')
    const move = useLayoutMove(naming)
    move.enabled.value = true
    await settle()
    naming.value = 'title'
    await settle()
    finishFirst(answer(99))
    await settle()
    expect(move.preview.value?.to_move).toBe(2)
    expect(move.loading.value).toBe(false)
  })

  it('says so when the library cannot be checked, and reset clears it all', async () => {
    vi.spyOn(api.library, 'movePreview').mockRejectedValue(new Error('boom'))
    const move = useLayoutMove(ref<NamingPreset>('author_folder'))
    move.enabled.value = true
    await settle()
    expect(move.error.value).toContain('boom')
    move.reset()
    expect([move.enabled.value, move.preview.value, move.error.value, move.loading.value]).toEqual([false, null, '', false])
  })
})
