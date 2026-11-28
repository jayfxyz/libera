import { describe, expect, it } from 'vitest'
import { bookFilesTree, formatBytes } from '../fileTree'

describe('formatBytes', () => {
  it('uses the largest unit that keeps the number small', () => {
    expect([0, 512, 1024, 1536, 150 * 1024, 5 * 1024 * 1024, 412 * 1024 * 1024, 2.5 * 1024 ** 3].map(formatBytes)).toEqual([
      '0 B', '512 B', '1.0 KB', '1.5 KB', '150 KB', '5.0 MB', '412 MB', '2.5 GB',
    ])
  })
})

describe('bookFilesTree', () => {
  it('nests the folders and puts the files in the book folder', () => {
    const tree = bookFilesTree({
      root: '/audiobooks',
      folders: ['Dan Brown', 'Angels & Demons [B0016LC2QG]'],
      files: [
        { name: 'Angels & Demons [B0016LC2QG].m4b', size_bytes: 1000, kind: 'audio' },
        { name: 'cover.jpg', size_bytes: 20, kind: 'cover' },
      ],
      found: true,
    })
    expect(tree).toHaveLength(1)
    expect(tree[0]).toMatchObject({ name: 'Dan Brown', kind: 'folder' })
    const book = tree[0]!.children[0]!
    expect(book.name).toBe('Angels & Demons [B0016LC2QG]')
    expect(book.children.map((file) => [file.name, file.kind, file.size])).toEqual([
      ['Angels & Demons [B0016LC2QG].m4b', 'audio', 1000],
      ['cover.jpg', 'cover', 20],
    ])
  })

  it('lists the files straight under the root when there are no folders', () => {
    const tree = bookFilesTree({ root: '/x', folders: [], files: [{ name: 'a.m4b', size_bytes: 1, kind: 'audio' }], found: true })
    expect(tree.map((node) => node.name)).toEqual(['a.m4b'])
  })
})
