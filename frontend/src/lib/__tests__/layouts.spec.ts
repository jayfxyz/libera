import { describe, expect, it } from 'vitest'
import { bookFolders, layoutTree, LAYOUTS, RECOMMENDED_LAYOUT, SAMPLE_BOOKS } from '../layouts'

const [fellowship, , angels] = SAMPLE_BOOKS

describe('bookFolders', () => {
  it('names every layout the way the server does', () => {
    const got = Object.fromEntries(LAYOUTS.map((layout) => [layout.id, bookFolders(layout.id, fellowship!).join('/')]))
    expect(got).toEqual({
      title: 'The Fellowship of the Ring [B007978NPG]',
      author_folder: 'J.R.R. Tolkien/The Fellowship of the Ring [B007978NPG]',
      author_folder_year: 'J.R.R. Tolkien/1954 - The Fellowship of the Ring [B007978NPG]',
      author_series: 'J.R.R. Tolkien/The Lord of the Rings/01 - The Fellowship of the Ring [B007978NPG]',
      author_series_year: 'J.R.R. Tolkien/The Lord of the Rings/01 - 1954 - The Fellowship of the Ring [B007978NPG]',
    })
  })

  it('turns a colon into " - " and a slash into "_"', () => {
    const book = { ...angels!, title: 'Dune: Part One', author: 'AC/DC' }
    expect(bookFolders('author_folder', book)).toEqual(['AC_DC', 'Dune - Part One [B0016LC2QG]'])
  })

  it('leaves a book with no series out of the series folder', () => {
    const standalone = { ...angels!, series: '', seriesIndex: '' }
    expect(bookFolders('author_series', standalone)).toEqual(['Dan Brown', 'Angels & Demons [B0016LC2QG]'])
  })
})

describe('layoutTree', () => {
  it('puts the audio file and cover in each book folder', () => {
    const [tolkien] = layoutTree('author_folder')
    expect(tolkien!.name).toBe('J.R.R. Tolkien')
    expect(tolkien!.children.map((book) => book.name)).toEqual([
      'The Fellowship of the Ring [B007978NPG]',
      'The Two Towers [B007978NQK]',
    ])
    expect(tolkien!.children[0]!.children.map((file) => file.name)).toEqual([
      'The Fellowship of the Ring [B007978NPG].m4b',
      'cover.jpg',
    ])
  })

  it('shares a series folder between its books', () => {
    const [tolkien] = layoutTree('author_series')
    expect(tolkien!.children).toHaveLength(1)
    expect(tolkien!.children[0]!.children).toHaveLength(2)
  })

  it('recommends a layout that exists', () => {
    expect(LAYOUTS.find((layout) => layout.id === RECOMMENDED_LAYOUT)?.recommended).toBe(true)
  })
})
