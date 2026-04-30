import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from '@dagrejs/dagre'
import { API_BASE } from '../pages/tabs/shared'

interface GraphData {
  nodes: { id: string; label: string; type: string; color: string; aliases?: string[]; attributes?: Record<string, unknown> }[]
  edges: { source: string; target: string; label: string }[]
}

interface EntityNodeProps {
  data: { label: string; entityType: string; color: string }
}

const TYPE_ICONS: Record<string, string> = {
  person: '\u{1F464}',
  organization: '\u{1F3E2}',
  location: '\u{1F4CD}',
  event: '\u{23F0}',
  unknown: '\u{2753}',
}

function EntityNode({ data }: EntityNodeProps) {
  const icon = TYPE_ICONS[data.entityType] || TYPE_ICONS.unknown
  return (
    <div className="px-3 py-2 rounded-lg border-2 shadow-md bg-white dark:bg-slate-800 cursor-pointer transition-all hover:shadow-lg hover:scale-105"
      style={{ borderColor: data.color }}>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-slate-400" />
      <div className="flex items-center gap-1.5">
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 max-w-[120px] truncate">{data.label}</span>
      </div>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-slate-400" />
    </div>
  )
}

const nodeTypes: NodeTypes = {
  entity: EntityNode,
}

function layoutGraph(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 100, marginx: 40, marginy: 40 })

  for (const n of nodes) {
    g.setNode(n.id, { width: 160, height: 40 })
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target)
  }

  dagre.layout(g)

  const layoutedNodes = nodes.map(n => {
    const pos = g.node(n.id)
    return {
      ...n,
      position: { x: pos.x - 80, y: pos.y - 20 },
    }
  })

  return { nodes: layoutedNodes, edges }
}

interface KnowledgeGraphProps {
  kbId: string
  onNodeClick?: (node: Node) => void
  refreshKey?: number
}

export function KnowledgeGraph({ kbId, onNodeClick, refreshKey }: KnowledgeGraphProps) {
  const [rawData, setRawData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)

  useEffect(() => {
    setLoading(true)
    fetch(`${API_BASE}/api/graph/${kbId}`)
      .then(r => r.json())
      .then(data => { setRawData(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [kbId, refreshKey])

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node)
    onNodeClick?.(node)
  }, [onNodeClick])

  const { nodes: flowNodes, edges: flowEdges } = useMemo(() => {
    if (!rawData) return { nodes: [], edges: [] }

    const searchLower = search.toLowerCase()
    const matchingIdSet = new Set<string>()

    if (searchLower) {
      rawData.nodes.forEach(n => {
        if (n.label.toLowerCase().includes(searchLower) || n.type.toLowerCase().includes(searchLower)) {
          matchingIdSet.add(n.id)
          rawData.edges.forEach(e => {
            if (e.source === n.id) matchingIdSet.add(e.target)
            if (e.target === n.id) matchingIdSet.add(e.source)
          })
        }
      })
    }

    const nodes: Node[] = rawData.nodes.map(n => {
      const isMatch = !searchLower || matchingIdSet.has(n.id)
      return {
        id: n.id,
        type: 'entity',
        position: { x: 0, y: 0 },
        data: { label: n.label, entityType: n.type, color: n.color },
        opacity: searchLower && !isMatch ? 0.15 : 1,
      }
    })

    const edges: Edge[] = rawData.edges
      .filter(e => {
        const sourceExists = nodes.some(n => n.id === e.source)
        const targetExists = nodes.some(n => n.id === e.target)
        return sourceExists && targetExists
      })
      .map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fill: '#64748b' },
      }))

    return layoutGraph(nodes, edges)
  }, [rawData, search])

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges)

  useEffect(() => { setNodes(flowNodes) }, [flowNodes, setNodes])
  useEffect(() => { setEdges(flowEdges) }, [flowEdges, setEdges])

  if (loading) return <div className="flex items-center justify-center h-full text-stone-400">Loading graph...</div>
  if (!rawData || rawData.nodes.length === 0) return <div className="flex items-center justify-center h-full text-stone-400">No graph data. Compile first.</div>

  return (
    <div className="h-full flex flex-col">
      {/* Search bar */}
      <div className="px-3 py-2 border-b border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search entities..."
          className="w-full px-3 py-1.5 text-sm rounded-lg border border-stone-200 dark:border-slate-600 bg-stone-50 dark:bg-slate-700 text-stone-700 dark:text-stone-200 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-amber-400"
        />
      </div>

      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.2}
          maxZoom={3}
          className="bg-stone-50 dark:bg-slate-900"
        >
          <Controls className="!bg-white dark:!bg-slate-800 !border-stone-200 dark:!border-slate-700 [&>button]:!bg-white dark:[&>button]:!bg-slate-800 [&>button]:!border-stone-200 dark:[&>button]:!border-slate-700 [&>button:hover]:!bg-stone-100 dark:[&>button:hover]:!bg-slate-700" />
          <MiniMap
            nodeColor={(n: Node) => (n.data as { color?: string })?.color || '#8b5cf6'}
            className="!bg-white dark:!bg-slate-800 !border-stone-200 dark:!border-slate-700"
            maskColor="rgba(0,0,0,0.1)"
          />
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color={"#d6d3d1"} />
        </ReactFlow>

        {/* Detail panel */}
        {selectedNode && (
          <div className="absolute top-3 right-3 w-64 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-stone-200 dark:border-slate-700 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-stone-700 dark:text-stone-200">{String(selectedNode.data?.label || '')}</span>
              <button onClick={() => setSelectedNode(null)} className="text-stone-400 hover:text-stone-600 text-xs">✕</button>
            </div>
            <div className="text-xs text-stone-500 dark:text-stone-400 space-y-1">
              <div>Type: <span className="font-medium text-stone-700 dark:text-stone-300">{String(selectedNode.data?.entityType || 'unknown')}</span></div>
              <div className="flex items-center gap-1.5">
                <span>Color:</span>
                <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: String(selectedNode.data?.color || '#8b5cf6') }} />
              </div>
              {/* Connected edges */}
              <div className="mt-2 pt-2 border-t border-stone-100 dark:border-slate-700">
                <div className="font-medium text-stone-600 dark:text-slate-300 mb-1">Connections:</div>
                {edges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).slice(0, 8).map(e => {
                  const otherId = e.source === selectedNode.id ? e.target : e.source
                  const otherNode = nodes.find(n => n.id === otherId)
                  return (
                    <div key={e.id} className="text-stone-500 dark:text-stone-400">
                      {String(e.label || 'related')} → {String(otherNode?.data?.label || otherId)}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Stats bar */}
      <div className="px-3 py-1.5 border-t border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-stone-400 flex gap-4">
        <span>{rawData.nodes.length} nodes</span>
        <span>{rawData.edges.length} edges</span>
      </div>
    </div>
  )
}
