import { useState, useCallback } from 'react'
import { API_BASE } from '../pages/tabs/shared'

interface ChunkData {
  chunk_id: string
  doc_id: string
  content: string
}

const CITATION_PATTERN = /\b(doc_\d+)[/\s](?:chunk[_\s]?(\d+))\b|\[doc_id[:\s]*(\w+)(?:[,\s]+chunk[:\s]*(\w+))?\]/gi

export function EvidenceLink({ text }: { text: string }) {
  const [activeChunk, setActiveChunk] = useState<ChunkData | null>(null)
  const [loading, setLoading] = useState(false)
  const [kbId, setKbId] = useState<string>('')

  // Try to get kbId from session storage (set by KB detail page)
  useState(() => {
    const stored = sessionStorage.getItem('currentKbId')
    if (stored) setKbId(stored)
  })

  const fetchChunk = useCallback(async (docId: string, chunkId: string) => {
    if (!kbId) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${kbId}/${docId}/chunks/${chunkId}`)
      if (res.ok) {
        const data = await res.json()
        setActiveChunk(data)
      }
    } catch {
      // Silently fail
    }
    setLoading(false)
  }, [kbId])

  // Split text by citation patterns and render
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  const regex = new RegExp(CITATION_PATTERN.source, CITATION_PATTERN.flags)

  while ((match = regex.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>)
    }

    const docId = match[1] || match[3] || ''
    const chunkId = match[2] || match[4] || ''
    const fullMatch = match[0]

    parts.push(
      <button
        key={`c-${match.index}`}
        onClick={() => fetchChunk(docId, chunkId)}
        className="inline-flex items-center px-1 py-0.5 mx-0.5 text-xs font-mono bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors border border-blue-200 dark:border-blue-800"
        title={`Click to view source: ${docId}/chunk_${chunkId}`}
      >
        {fullMatch}
      </button>
    )

    lastIndex = regex.lastIndex
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex)}</span>)
  }

  return (
    <>
      {parts}
      {activeChunk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setActiveChunk(null)}>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-stone-200 dark:border-slate-700 w-[600px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-stone-200 dark:border-slate-700">
              <div>
                <h3 className="text-sm font-semibold text-stone-700 dark:text-stone-200">Source: {activeChunk.doc_id}</h3>
                <span className="text-xs text-stone-400">Chunk {activeChunk.chunk_id}</span>
              </div>
              <button onClick={() => setActiveChunk(null)} className="text-stone-400 hover:text-stone-600 text-lg">&times;</button>
            </div>
            <div className="p-4 overflow-y-auto text-sm text-stone-700 dark:text-stone-300 leading-relaxed whitespace-pre-wrap">
              {activeChunk.content}
            </div>
          </div>
        </div>
      )}
      {loading && (
        <div className="fixed bottom-4 left-4 z-50 bg-white dark:bg-slate-800 rounded-lg shadow-lg px-3 py-2 text-xs text-stone-500 dark:text-stone-400 border border-stone-200 dark:border-slate-700">
          Loading source...
        </div>
      )}
    </>
  )
}
