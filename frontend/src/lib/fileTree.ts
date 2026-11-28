import type { BookFiles } from '@/api/client'

export interface TreeNode {
  name: string
  kind: 'folder' | 'audio' | 'cover' | 'pdf' | 'other'
  children: TreeNode[]
  size?: number // bytes, for a real file
}

/** A name in two parts, so a long one can be cut in the middle and still end with its ID and extension:
 *  "A very long title [B017TDZGTA].m4b" → ["A very long title", " [B017TDZGTA].m4b"]. */
export function splitName(name: string): { head: string; tail: string } {
  const match = /^(.*?)((?: \[[^[\]]+\])?(?:\.[^.\s[\]]+){0,2})$/.exec(name)
  return { head: match?.[1] ?? name, tail: match?.[2] ?? '' }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`
}

/** The folders from the root down to the book's own, with its files inside. */
export function bookFilesTree(listing: BookFiles): TreeNode[] {
  const files: TreeNode[] = listing.files.map((file) => ({ name: file.name, kind: file.kind, children: [], size: file.size_bytes }))
  return listing.folders.reduceRight<TreeNode[]>((inner, name) => [{ name, kind: 'folder', children: inner }], files)
}
