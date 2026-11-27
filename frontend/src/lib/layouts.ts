import type { NamingPreset } from '@/api/client'

/** The folder layouts, in the order they are offered. Mirrors server/app/jobs/filename.py. */
export interface Layout {
  id: NamingPreset
  name: string
  why: string
  recommended?: boolean
  /** Shown under "Other options". */
  other?: boolean
  author: boolean
  series: boolean
  year: boolean
}

export const LAYOUTS: Layout[] = [
  {
    id: 'author_folder', name: 'Author / Title', recommended: true,
    why: 'Works with every server we checked.', author: true, series: false, year: false,
  },
  {
    id: 'title', name: 'Title',
    why: 'Flat and no author folder. The author comes from the tags.', author: false, series: false, year: false,
  },
  {
    id: 'author_series', name: 'Author / Series / Number - Title',
    why: 'Series order from the path.', author: true, series: true, year: false,
  },
  {
    id: 'author_folder_year', name: 'Author / Year - Title', other: true,
    why: 'Adds the publication year.', author: true, series: false, year: true,
  },
  {
    id: 'author_series_year', name: 'Author / Series / Number - Year - Title', other: true,
    why: 'Series order and the year.', author: true, series: true, year: true,
  },
]

export const RECOMMENDED_LAYOUT: NamingPreset = 'author_folder'

export interface SampleBook {
  title: string
  author: string
  series: string
  seriesIndex: string
  year: string
  asin: string
}

/** Well-known books (example IDs) used to show what a layout looks like. */
export const SAMPLE_BOOKS: SampleBook[] = [
  { title: 'The Fellowship of the Ring', author: 'J.R.R. Tolkien', series: 'The Lord of the Rings', seriesIndex: '1', year: '1954', asin: 'B007978NPG' },
  { title: 'The Two Towers', author: 'J.R.R. Tolkien', series: 'The Lord of the Rings', seriesIndex: '2', year: '1954', asin: 'B007978NQK' },
  { title: 'Angels & Demons', author: 'Dan Brown', series: 'Robert Langdon', seriesIndex: '1', year: '2000', asin: 'B0016LC2QG' },
]

export interface TreeNode {
  name: string
  kind: 'folder' | 'audio' | 'cover'
  children: TreeNode[]
}

export function layoutById(id: NamingPreset): Layout {
  return LAYOUTS.find((layout) => layout.id === id) ?? LAYOUTS[0]!
}

/** A colon becomes " - " and characters Windows and SMB reject become "_" (server/app/naming.py). */
function cleanName(name: string): string {
  return name.replace(/\s*:\s*/g, ' - ').replace(/[<>"/\\|?*]/g, '_')
}

/** "2" becomes "02" and "2.5" becomes "02.5", so a series sorts in order. */
function padNumber(index: string): string {
  return /^\d+(\.\d+)?$/.test(index) ? index.replace(/^\d+/, (whole) => whole.padStart(2, '0')) : index
}

function folderNames(layout: Layout, book: SampleBook): string[] {
  const folders = layout.author ? [cleanName(book.author)] : []
  if (layout.series && book.series) folders.push(cleanName(book.series))
  return folders
}

function leafName(layout: Layout, book: SampleBook): string {
  const lead = []
  if (layout.series && book.series) lead.push(padNumber(book.seriesIndex))
  if (layout.year) lead.push(book.year)
  return `${[...lead, cleanName(book.title)].join(' - ')} [${book.asin}]`
}

/** The folders a book's files go in, outermost first; the last one is the book's own. */
export function bookFolders(id: NamingPreset, book: SampleBook): string[] {
  const layout = layoutById(id)
  return [...folderNames(layout, book), leafName(layout, book)]
}

function childNamed(parent: TreeNode, name: string, kind: TreeNode['kind']): TreeNode {
  let child = parent.children.find((node) => node.name === name && node.kind === kind)
  if (!child) {
    child = { name, kind, children: [] }
    parent.children.push(child)
  }
  return child
}

function addBook(root: TreeNode, id: NamingPreset, book: SampleBook): void {
  const folders = bookFolders(id, book)
  const bookFolder = folders.reduce((parent, name) => childNamed(parent, name, 'folder'), root)
  bookFolder.children.push(
    { name: `${folders[folders.length - 1]}.m4b`, kind: 'audio', children: [] },
    { name: 'cover.jpg', kind: 'cover', children: [] },
  )
}

/** What the sample library looks like on disk with this layout. */
export function layoutTree(id: NamingPreset, books: SampleBook[] = SAMPLE_BOOKS): TreeNode[] {
  const root: TreeNode = { name: '', kind: 'folder', children: [] }
  for (const book of books) addBook(root, id, book)
  return root.children
}
