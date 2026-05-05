import { useState } from 'react'
import { parseExcelSheets } from './parseExcelMarkdown'
import { SheetTabs } from './SheetTabs'
import { VirtualExcelTable } from './VirtualExcelTable'

interface ExcelViewerProps {
  markdown: string
}

export function ExcelViewer({ markdown }: ExcelViewerProps) {
  const sheets = parseExcelSheets(markdown)
  const [activeSheet, setActiveSheet] = useState(0)

  if (sheets.length === 0) {
    return <div className="excel-viewer__empty">{'无Excel数据'}</div>
  }

  const current = sheets[activeSheet]

  return (
    <div className="excel-viewer">
      <div className="excel-viewer__header">
        <SheetTabs
          sheets={sheets}
          activeIndex={activeSheet}
          onSelect={setActiveSheet}
        />
        <span className="excel-viewer__stats">
          {current.rows.length} 行 × {current.headers.length} 列
        </span>
      </div>
      <VirtualExcelTable
        headers={current.headers}
        rows={current.rows}
      />
    </div>
  )
}
