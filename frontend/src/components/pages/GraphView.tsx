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
      <div className="flex flex-col items-center justify-center h-full">
        <GraphIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium">暂无知识库，请先创建</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <GraphIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium mb-4">选择知识库查看图谱</p>
        <select
          value=""
          onChange={(e) => setCurrentKbId(e.target.value)}
          className="px-4 py-2 rounded-lg border border-stone-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm"
        >
          <option value="">请选择...</option>
          {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-800 dark:text-stone-100">知识图谱</h1>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={currentKbId}
            onChange={(e) => setCurrentKbId(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-stone-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-xs"
          >
            {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
          </select>
          <button
            onClick={() => setRefreshKey(k => k + 1)}
            className="px-3 py-1.5 bg-stone-100 hover:bg-stone-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-stone-600 dark:text-stone-300 rounded-lg text-xs font-medium transition-colors"
          >
            刷新
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <KnowledgeGraph kbId={currentKbId} refreshKey={refreshKey} />
      </div>
    </div>
  )
}
