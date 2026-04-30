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
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/30" onClick={onClose}>
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-stone-200 dark:border-slate-700 w-[560px] max-h-[60vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-4 py-3 border-b border-stone-200 dark:border-slate-700">
          <span className="text-stone-400 text-sm">⌘K</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search entities, wiki pages..."
            className="flex-1 bg-transparent text-stone-800 dark:text-stone-100 text-sm outline-none placeholder:text-stone-400"
          />
          {loading && <div className="animate-spin h-4 w-4 border-2 border-amber-500 border-t-transparent rounded-full" />}
        </div>
        <div className="overflow-y-auto max-h-[45vh]">
          {results.length === 0 && query.length >= 2 && !loading && (
            <div className="px-4 py-8 text-center text-sm text-stone-400">No results found</div>
          )}
          {results.map((r, i) => (
            <button
              key={`${r.type}-${r.id}-${i}`}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-stone-50 dark:hover:bg-slate-700/50 transition-colors text-left"
              onClick={onClose}
            >
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                r.type === 'entity' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              }`}>{r.type}</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-stone-700 dark:text-stone-200 truncate">{r.title}</div>
                {r.snippet && <div className="text-xs text-stone-400 truncate">{r.snippet}</div>}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
