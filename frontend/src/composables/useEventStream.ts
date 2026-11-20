import type { BookSummary, Download } from '@/api/client'

/** What each event type carries: the whole resource, as its REST endpoint returns it. */
export interface StreamEvents {
  'download.updated': Download
  'book.updated': BookSummary
}

type Handler = (data: never) => void

const handlers = new Map<string, Set<Handler>>()
const openHandlers = new Set<() => void>()
let source: EventSource | null = null

function connect() {
  if (source) return
  source = new EventSource('/api/events')
  // Fires on the first connection and on every automatic reconnect.
  source.onopen = () => openHandlers.forEach((handler) => handler())
  source.onmessage = (message: MessageEvent<string>) => {
    let event: { type: string; data: unknown }
    try {
      event = JSON.parse(message.data)
    } catch {
      return // not ours
    }
    handlers.get(event.type)?.forEach((handler) => (handler as (data: unknown) => void)(event.data))
  }
}

/**
 * The app's one Server-Sent Events stream (GET /api/events). Every message is
 * {type, id, data}. EventSource reconnects by itself; the stream has no replay,
 * so stores reload their snapshot in onOpen, which runs on every (re)connect.
 */
export function useEventStream() {
  connect()

  /** Call handler with each event of this type. Returns a function that stops it. */
  function on<K extends keyof StreamEvents>(type: K, handler: (data: StreamEvents[K]) => void): () => void {
    const set = handlers.get(type) ?? new Set<Handler>()
    handlers.set(type, set)
    set.add(handler as Handler)
    return () => set.delete(handler as Handler)
  }

  /** Call handler whenever the stream (re)opens. Returns a function that stops it. */
  function onOpen(handler: () => void): () => void {
    openHandlers.add(handler)
    return () => openHandlers.delete(handler)
  }

  return { on, onOpen }
}
