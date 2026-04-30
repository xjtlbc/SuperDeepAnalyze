import { KnowledgeGraph } from '../../graph/KnowledgeGraph'

export function GraphTab({ kbId, refreshKey = 0 }: { kbId: string; refreshKey?: number }) {
  return (
    <div className="h-full">
      <KnowledgeGraph kbId={kbId} refreshKey={refreshKey} />
    </div>
  )
}
