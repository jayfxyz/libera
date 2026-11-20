/**
 * Whether a copy of a resource stamped `incoming` should replace one stamped
 * `current`. A snapshot and an event can cross (the stream reconnects while a
 * reload is in flight), so the copy with the later updated_at wins; a copy
 * without a stamp (e.g. a download just queued here) always gives way.
 */
export function isNewer(incoming: string | null | undefined, current: string | null | undefined): boolean {
  if (!current || !incoming) return true
  return Date.parse(incoming) >= Date.parse(current)
}
