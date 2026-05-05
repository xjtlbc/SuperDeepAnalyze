import { useState, useEffect } from 'react'
import { API_BASE } from '../pages/tabs/shared'

interface ConceptTag {
  id: string
  name: string
  type: string
  frequency: number
  connections: number
  score: number
  rank: number
}

const TYPE_COLORS: Record<string, string> = {
  person: '#6366f1',
  organization: '#f59e0b',
  location: '#10b981',
  event: '#ef4444',
  unknown: '#8b5cf6',
}

export function ConceptTags({ kbId, entities, onTagClick, compact: _compact }: { kbId?: string; entities?: ConceptTag[]; onTagClick?: (name: string) => void; compact?: boolean }) {
  const [tags, setTags] = useState<ConceptTag[]>(entities || [])
  const [loading, setLoading] = useState(!entities)

  useEffect(() => {
    if (entities) { setTags(entities); setLoading(false); return }
    if (!kbId) return
    fetch(`${API_BASE}/api/wiki/${kbId}`)
      .then(r => r.json())
      .then(data => {
        if (data && data.top_entities) {
          setTags(data.top_entities.map((e: any, i: number) => ({
            ...e, rank: e.rank || i + 1
          })))
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [kbId, entities])

  if (loading) {
    return <div style={{ padding: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {[...Array(5)].map((_, i) => (
        <div key={i} style={{
          height: 24, width: 80, borderRadius: 6,
          background: 'var(--bg-tertiary)', animation: 'pulse 1.5s infinite'
        }} />
      ))}
    </div>
  }

  if (!tags.length) return null

  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
        ☆ 核心概念
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {tags.slice(0, 15).map(tag => {
          const color = TYPE_COLORS[tag.type] || TYPE_COLORS.unknown
          return (
            <button
              key={tag.id}
              onClick={() => onTagClick?.(tag.name)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 10px',
                borderRadius: 12,
                background: `${color}15`,
                border: `1px solid ${color}30`,
                color,
                fontSize: 12,
                fontWeight: tag.rank <= 3 ? 600 : 400,
                cursor: 'pointer',
                transition: 'transform 0.15s ease, box-shadow 0.15s ease',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = 'scale(1.05)'
                e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = 'scale(1)'
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              <span style={{ fontSize: 10, opacity: 0.6 }}>#{tag.rank}</span>
              {tag.name}
              <span style={{ fontSize: 10, opacity: 0.6 }}>({tag.connections || tag.frequency})</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
