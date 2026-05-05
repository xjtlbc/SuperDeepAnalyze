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
  document: '\u{1F4C4}',
}

const TYPE_COLORS: Record<string, string> = {
  person: '#6366f1',
  organization: '#f59e0b',
  location: '#10b981',
  event: '#ef4444',
  unknown: '#8b5cf6',
  document: '#94a3b8',
}

function EntityNode({ data }: EntityNodeProps) {
  const icon = TYPE_ICONS[data.entityType] || TYPE_ICONS.unknown
  return (
    <div className="knowledge-graph__entity-node" style={{ borderColor: data.color }}>
      <Handle type="source" position={Position.Right} className="knowledge-graph__handle" />
      <div className="knowledge-graph__entity-inner">
        <span className="knowledge-graph__entity-icon">{icon}</span>
        <span className="knowledge-graph__entity-label">{data.label}</span>
      </div>
      <Handle type="target" position={Position.Left} className="knowledge-graph__handle" />
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
      .then(data => {
        if (data && data.nodes && data.edges) {
          setRawData(data)
        } else if (data && data.detail) {
          console.warn('Graph API error:', data.detail)
          setRawData(null)
        } else {
          setRawData(null)
        }
        setLoading(false)
      })
      .catch(() => { setRawData(null); setLoading(false) })
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
        data: {
          label: n.label,
          entityType: n.type,
          color: TYPE_COLORS[n.type] || n.color || TYPE_COLORS.unknown,
        },
        style: {
          width: 28 + Math.min(20, (rawData.edges.filter(e => e.source === n.id || e.target === n.id).length) * 3),
          height: 28 + Math.min(20, (rawData.edges.filter(e => e.source === n.id || e.target === n.id).length) * 3),
        },
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

  if (loading) return <div className="knowledge-graph__placeholder">Loading graph...</div>
  if (!rawData || rawData.nodes.length === 0) return <div className="knowledge-graph__placeholder">No graph data. Compile first.</div>

  return (
    <div className="knowledge-graph">
      {/* Search bar */}
      <div className="knowledge-graph__search-bar">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search entities..."
          className="knowledge-graph__search-input"
        />
      </div>

      <div className="knowledge-graph__canvas-wrapper">
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
          className="knowledge-graph__flow"
        >
          <Controls className="knowledge-graph__controls" />
          <MiniMap
            nodeColor={(n: Node) => (n.data as { color?: string })?.color || '#8b5cf6'}
            className="knowledge-graph__minimap"
            maskColor="rgba(0,0,0,0.1)"
          />
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color={"#d6d3d1"} />
        </ReactFlow>

        {/* Detail panel */}
        {selectedNode && (
          <div className="knowledge-graph__detail-panel">
            <div className="knowledge-graph__detail-header">
              <span className="knowledge-graph__detail-title">{String(selectedNode.data?.label || '')}</span>
              <button onClick={() => setSelectedNode(null)} className="knowledge-graph__detail-close">{'✕'}</button>
            </div>
            <div className="knowledge-graph__detail-body">
              <div className="knowledge-graph__detail-row">Type: <span className="knowledge-graph__detail-value">{String(selectedNode.data?.entityType || 'unknown')}</span></div>
              <div className="knowledge-graph__detail-row knowledge-graph__detail-row--color">
                <span>Color:</span>
                <span className="knowledge-graph__color-swatch" style={{ backgroundColor: String(selectedNode.data?.color || '#8b5cf6') }} />
              </div>
              {/* Connected edges */}
              <div className="knowledge-graph__detail-connections">
                <div className="knowledge-graph__detail-connections-title">Connections:</div>
                {edges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).slice(0, 8).map(e => {
                  const otherId = e.source === selectedNode.id ? e.target : e.source
                  const otherNode = nodes.find(n => n.id === otherId)
                  return (
                    <div key={e.id} className="knowledge-graph__detail-connection">
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
      <div className="knowledge-graph__stats-bar">
        <span>{rawData.nodes.length} nodes</span>
        <span>{rawData.edges.length} edges</span>
      </div>
    </div>
  )
}
