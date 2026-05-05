import { useState, useEffect, useRef } from 'react'
import { API_BASE } from './pages/tabs/shared'

interface SearchResult {
  type: string
  id: string
  title: string
  snippet: string
}

export function SearchDialog({ open, onClose, kbId }: { open: boolean; onClose: () => void; kbId?: string }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQuery('')
      setResults([])
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open])

  useEffect(() => {
    if (!query.trim() || query.length < 2 || !kbId) {
      setResults([])
      return
    }
    const timer = setTimeout(() => {
      setLoading(true)
      fetch(`${API_BASE}/api/wiki/${kbId}/search?q=${encodeURIComponent(query)}&limit=15`)
        .then(r => r.json())
        .then(data => setResults(data.results || []))
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [query, kbId])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (open) window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="search-dialog__overlay" onClick={onClose}>
      <div className="search-dialog__panel" onClick={e => e.stopPropagation()}>
        <div className="search-dialog__input-row">
          <span className="search-dialog__shortcut-hint">{'⌘K'}</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search entities, wiki pages..."
            className="search-dialog__input"
          />
          {loading && <div className="chat-spinner chat-spinner--accent" />}
        </div>
        <div className="search-dialog__results">
          {results.length === 0 && query.length >= 2 && !loading && (
            <div className="search-dialog__empty">No results found</div>
          )}
          {results.map((r, i) => (
            <button
              key={`${r.type}-${r.id}-${i}`}
              className="search-dialog__result-item"
              onClick={onClose}
            >
              <span className={`search-dialog__result-badge ${r.type === 'entity' ? 'search-dialog__result-badge--entity' : 'search-dialog__result-badge--page'}`}>{r.type}</span>
              <div className="search-dialog__result-content">
                <div className="search-dialog__result-title">{r.title}</div>
                {r.snippet && <div className="search-dialog__result-snippet">{r.snippet}</div>}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
