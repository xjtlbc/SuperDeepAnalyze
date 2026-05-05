import { useState, useEffect } from 'react'
import { X, FileText, Clock, Database } from 'lucide-react'
import { API_BASE } from '../pages/tabs/shared'

interface DocInfo {
  id: string
  filename: string
  file_size: number
  file_type: string
  parse_status: string
  compile_status: string
  chunk_count?: number
  created_at?: string
}

export function DocumentDrawer({ docId, kbId, onClose }: { docId: string; kbId: string; onClose: () => void }) {
  const [doc, setDoc] = useState<DocInfo | null>(null)
  const [l1Count, setL1Count] = useState(0)
  const [l2Count, setL2Count] = useState(0)

  useEffect(() => {
    fetch(`${API_BASE}/api/documents/${docId}/detail?kb_id=${kbId}`)
      .then(r => r.json())
      .then(data => {
        setDoc(data.document || data)
        setL1Count(data.l1_summary?.batch_count || 0)
        setL2Count(data.l2_summary?.chunk_count || 0)
      })
      .catch(() => {})
  }, [docId, kbId])

  if (!doc) return null

  const fileTypeColor = (t: string) => {
    const m: Record<string, string> = { pdf: '#e03131', doc: '#1c7ed6', docx: '#1c7ed6',
      xls: '#2f9e44', xlsx: '#2f9e44', audio: '#e8590c', image: '#7950f2', text: '#868e96' }
    return m[t] || '#868e96'
  }

  return (
    <div style={{
      position: 'fixed', right: 0, top: 48, bottom: 0, width: 420,
      background: 'var(--bg)', borderLeft: '1px solid var(--border)',
      boxShadow: 'var(--shadow-lg)', zIndex: 'var(--z-sticky)',
      overflow: 'auto', display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: doc.compile_status === 'completed' ? 'var(--success)' : 'var(--text-muted)'
          }} />
          <FileText size={16} color={fileTypeColor(doc.file_type)} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>文档详情</span>
        </div>
        <button onClick={onClose} style={{ padding: 4, cursor: 'pointer' }}>
          <X size={16} />
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        <p style={{ fontSize: 14, fontWeight: 500, margin: '0 0 12px' }}>{doc.filename}</p>
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 12 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)' }}>
            <Database size={12} /> {doc.file_type?.toUpperCase()}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)' }}>
            <Clock size={12} /> {((doc.file_size || 0) / 1024).toFixed(0)}KB
          </span>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 16 }}>
          {[
            { label: 'L1 批次', value: l1Count, color: '#7950f2' },
            { label: 'L2 分块', value: l2Count, color: '#2f9e44' },
            { label: '状态', value: doc.compile_status === 'completed' ? '已完成' : '处理中', color: doc.compile_status === 'completed' ? '#10b981' : '#f59e0b' },
          ].map(s => (
            <div key={s.label} style={{
              textAlign: 'center', padding: '10px 6px', borderRadius: 8,
              background: `${s.color}10`, border: `1px solid ${s.color}20`
            }}>
              <p style={{ fontSize: 18, fontWeight: 700, color: s.color, margin: '0 0 2px' }}>
                {typeof s.value === 'string' ? s.value : s.value}
              </p>
              <p style={{ fontSize: 10, color: 'var(--text-muted)', margin: 0 }}>{s.label}</p>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 12, borderBottom: '1px solid var(--border)' }}>
          {['L1 摘要', 'L2 原文'].map(t => (
            <button key={t} style={{
              padding: '6px 12px', fontSize: 12, borderBottom: '2px solid var(--accent)',
              background: 'none', cursor: 'pointer', fontWeight: 500
            }}>{t}</button>
          ))}
          <button style={{ padding: '6px 12px', fontSize: 12, border: 'none', background: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
            L2 原文
          </button>
        </div>

        {doc.compile_status === 'completed' ? (
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            该文档已完成编译，共 {l2Count} 个文本块，{l1Count} 批摘要。
            在 Agent 对话中可通过 read_l1 / read_l2 工具深入阅读。
          </p>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>文档正在处理中...</p>
        )}
      </div>
    </div>
  )
}
