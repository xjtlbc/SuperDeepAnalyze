interface DocAbstract {
  doc_id: string
  abstract: string
  token_count?: number
  entities_top5?: string[]
  doc_type?: string
}

interface DocAbstractCardsProps {
  abstracts: DocAbstract[]
  onSelectDoc?: (docId: string) => void
}

export default function DocAbstractCards({ abstracts, onSelectDoc }: DocAbstractCardsProps) {
  if (!abstracts || abstracts.length === 0) {
    return null
  }

  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px',
      padding: '8px 0',
    }}>
      {abstracts.map((doc) => (
        <div
          key={doc.doc_id}
          onClick={() => onSelectDoc?.(doc.doc_id)}
          style={{
            flex: '1 1 200px',
            maxWidth: '300px',
            padding: '8px 10px',
            background: 'rgba(59,130,246,0.08)',
            border: '1px solid rgba(59,130,246,0.2)',
            borderRadius: '6px',
            cursor: onSelectDoc ? 'pointer' : 'default',
            transition: 'background 0.2s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLDivElement).style.background = 'rgba(59,130,246,0.15)'
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLDivElement).style.background = 'rgba(59,130,246,0.08)'
          }}
        >
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '4px',
          }}>
            <span style={{ fontSize: '11px', color: '#60a5fa', fontWeight: 600 }}>
              {doc.doc_id}
            </span>
            {doc.doc_type && (
              <span style={{
                fontSize: '10px',
                color: '#9ca3af',
                background: 'rgba(156,163,175,0.15)',
                padding: '1px 5px',
                borderRadius: '3px',
              }}>
                {doc.doc_type}
              </span>
            )}
          </div>

          <div style={{
            fontSize: '12px',
            color: '#d1d5db',
            lineHeight: '1.4',
            maxHeight: '60px',
            overflow: 'hidden',
          }}>
            {doc.abstract}
          </div>

          {doc.entities_top5 && doc.entities_top5.length > 0 && (
            <div style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '3px',
              marginTop: '4px',
            }}>
              {doc.entities_top5.slice(0, 4).map((entity, i) => (
                <span key={i} style={{
                  fontSize: '10px',
                  color: '#a78bfa',
                  background: 'rgba(167,139,250,0.12)',
                  padding: '1px 5px',
                  borderRadius: '8px',
                }}>
                  {entity}
                </span>
              ))}
              {doc.entities_top5.length > 4 && (
                <span style={{ fontSize: '10px', color: '#6b7280' }}>
                  +{doc.entities_top5.length - 4}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
