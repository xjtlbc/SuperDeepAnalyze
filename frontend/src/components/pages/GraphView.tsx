import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/app'
import { GraphIcon } from '../Icons'
import { KnowledgeGraph } from '../graph/KnowledgeGraph'

const API_BASE = import.meta.env.VITE_API_BASE || ''

interface KB {
  id: string
  name: string
}

export function GraphView() {
  const { currentKbId, setCurrentKbId } = useAppStore()
  const [kbs, setKbs] = useState<KB[]>([])
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        setKbs(Array.isArray(data) ? data : [])
        if (!currentKbId && data.length > 0) setCurrentKbId(data[0].id)
      })
      .catch(console.error)
  }, [])

  if (kbs.length === 0) {
    return (
      <div className="graph-view__empty-state">
        <GraphIcon className="graph-view__empty-icon" />
        <p className="graph-view__empty-text">{'暂无知识库，请先创建'}</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="graph-view__empty-state">
        <GraphIcon className="graph-view__empty-icon" />
        <p className="graph-view__empty-text graph-view__empty-text--mb">{'选择知识库查看图谱'}</p>
        <select
          value=""
          onChange={(e) => setCurrentKbId(e.target.value)}
          className="graph-view__select"
        >
          <option value="">{'请选择...'}</option>
          {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
      </div>
    )
  }

  return (
    <div className="graph-view">
      <div className="graph-view__header">
        <div>
          <h1 className="graph-view__title">{'知识图谱'}</h1>
        </div>
        <div className="graph-view__header-actions">
          <select
            value={currentKbId}
            onChange={(e) => setCurrentKbId(e.target.value)}
            className="graph-view__select graph-view__select--sm"
          >
            {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
          </select>
          <button
            onClick={() => setRefreshKey(k => k + 1)}
            className="graph-view__refresh-btn"
          >
            {'刷新'}
          </button>
        </div>
      </div>
      <div className="graph-view__body">
        <KnowledgeGraph kbId={currentKbId} refreshKey={refreshKey} />
      </div>
    </div>
  )
}
