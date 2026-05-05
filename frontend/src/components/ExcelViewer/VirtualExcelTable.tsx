import { useRef, useCallback, useEffect, useState } from 'react'
import { parseCellAnnotations } from './parseExcelMarkdown'

interface VirtualExcelTableProps {
  headers: string[]
  rows: string[][]
  rowHeight?: number
  overscan?: number
}

export function VirtualExcelTable({
  headers,
  rows,
  rowHeight = 36,
  overscan = 15,
}: VirtualExcelTableProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(600)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })
    observer.observe(el)
    setContainerHeight(el.clientHeight)
    return () => observer.disconnect()
  }, [])

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop)
    }
  }, [])

  const startIdx = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan)
  const visibleCount = Math.ceil(containerHeight / rowHeight) + 2 * overscan
  const endIdx = Math.min(rows.length, startIdx + visibleCount)

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{ height: containerHeight, overflowY: 'auto', position: 'relative' }}
    >
      <table className="excel-table">
        <thead>
          <tr>
            <th className="excel-table__row-num">{'#'}</th>
            {headers.map((h, i) => (
              <th key={i} title={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* Top spacer */}
          {startIdx > 0 && (
            <tr>
              <td
                colSpan={headers.length + 1}
                style={{ height: startIdx * rowHeight, padding: 0, border: 'none' }}
              />
            </tr>
          )}
          {rows.slice(startIdx, endIdx).map((row, rowOffset) => {
            const actualIdx = startIdx + rowOffset
            return (
              <tr key={actualIdx} style={{ height: rowHeight }}>
                <td className="excel-table__row-num">{actualIdx + 1}</td>
                {row.map((cell, colIdx) => {
                  const { cleanText, annotations } = parseCellAnnotations(cell)
                  return (
                    <td key={colIdx} title={cleanText}>
                      {cleanText}
                      {annotations.map((a, ai) => (
                        <span
                          key={ai}
                          className={`excel-annotation ${a.type}`}
                          title={`${a.type}: ${a.value}`}
                        >
                          {a.type === 'fx' ? 'fx' : a.type === 'note' ? '💬' : '🔗'}
                        </span>
                      ))}
                    </td>
                  )
                })}
                {/* Pad missing columns */}
                {row.length < headers.length &&
                  Array.from({ length: headers.length - row.length }).map((_, i) => (
                    <td key={`pad-${i}`} />
                  ))}
              </tr>
            )
          })}
          {/* Bottom spacer */}
          {endIdx < rows.length && (
            <tr>
              <td
                colSpan={headers.length + 1}
                style={{
                  height: (rows.length - endIdx) * rowHeight,
                  padding: 0,
                  border: 'none',
                }}
              />
            </tr>
          )}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="excel-viewer__empty">
          {'此Sheet无数据'}
        </div>
      )}
    </div>
  )
}
