import { describe, expect, it } from 'vitest'
import { bookStatus } from '../bookStatus'

describe('bookStatus', () => {
  it('marks non-downloadable books as unavailable even after a prior error', () => {
    const status = bookStatus({ liberation_status: 'error', last_format: null, is_downloadable: false })
    expect(status.state).toBe('unavailable')
    expect(status.label).toBe('Not downloadable')
  })

  it('keeps already-downloaded books as downloaded even if no longer downloadable', () => {
    const status = bookStatus({ liberation_status: 'liberated', last_format: 'm4b', is_downloadable: false })
    expect(status.state).toBe('downloaded')
    expect(status.label).toBe('Downloaded · M4B')
  })

  it('marks downloadable books as none by default', () => {
    const status = bookStatus({ liberation_status: 'not_liberated', last_format: null, is_downloadable: true })
    expect(status.state).toBe('none')
  })
})
