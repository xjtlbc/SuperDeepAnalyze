import { useState, useEffect, useCallback } from 'react'
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

  // Read kbId from session storage on mount
  useEffect(() => {
    const stored = sessionStorage.getItem('currentKbId')
    if (stored) setKbId(stored)
  }, [])

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
        className="evidence-link__btn"
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
        <div className="evidence-link__modal-overlay" onClick={() => setActiveChunk(null)}>
          <div className="evidence-link__modal" onClick={e => e.stopPropagation()}>
            <div className="evidence-link__modal-header">
              <div>
                <h3 className="evidence-link__modal-title">Source: {activeChunk.doc_id}</h3>
                <span className="evidence-link__modal-subtitle">Chunk {activeChunk.chunk_id}</span>
              </div>
              <button onClick={() => setActiveChunk(null)} className="evidence-link__modal-close">&times;</button>
            </div>
            <div className="evidence-link__modal-body">
              {activeChunk.content}
            </div>
          </div>
        </div>
      )}
      {loading && (
        <div className="evidence-link__loading-toast">
          Loading source...
        </div>
      )}
    </>
  )
}
