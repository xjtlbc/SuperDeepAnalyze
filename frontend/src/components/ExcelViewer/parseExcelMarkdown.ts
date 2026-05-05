/**
 * Parse enriched Excel markdown into structured sheet data.
 *
 * Input format (from excel_processor.py):
 *   # Sheet: SheetName
 *   | col1 | col2 | col3 |
 *   |---|---|---|
 *   | val1 | val2 [fx:=SUM()] | val3 [note:comment] |
 */

export interface ParsedSheet {
  name: string
  headers: string[]
  rows: string[][]
}

export function parseExcelSheets(markdown: string): ParsedSheet[] {
  const sheets: ParsedSheet[] = []

  // Split by sheet headings
  const sections = markdown.split(/(?=# Sheet: )/)

  for (const section of sections) {
    const trimmed = section.trim()
    if (!trimmed) continue

    // Extract sheet name
    const nameMatch = trimmed.match(/^# Sheet: (.+)/m)
    const name = nameMatch ? nameMatch[1].trim() : 'Sheet'

    // Find all table rows
    const lines = trimmed.split('\n')
    const rows: string[][] = []
    let headerFound = false

    for (const line of lines) {
      const trimmedLine = line.trim()
      if (!trimmedLine.startsWith('|')) continue

      // Skip separator row
      if (/^\|[\s\-:|]+\|$/.test(trimmedLine)) continue

      // Parse cells
      const cells = trimmedLine
        .split('|')
        .slice(1, -1) // Remove empty first/last from split
        .map(cell => cell.trim())

      if (!headerFound) {
        headerFound = true
      }

      rows.push(cells)
    }

    if (rows.length > 0) {
      sheets.push({
        name,
        headers: rows[0],
        rows: rows.slice(1),
      })
    }
  }

  return sheets
}

/**
 * Extract annotation badges from a cell value.
 * Returns { text, annotations: [{type, value}] }
 */
export function parseCellAnnotations(cellValue: string): {
  cleanText: string
  annotations: Array<{ type: 'fx' | 'note' | 'link'; value: string }>
} {
  const annotations: Array<{ type: 'fx' | 'note' | 'link'; value: string }> = []

  // Match [fx:formula], [note:comment], [link:url]
  const annoRegex = /\[(fx|note|link):([^\]]+)\]/g
  let match
  while ((match = annoRegex.exec(cellValue)) !== null) {
    annotations.push({
      type: match[1] as 'fx' | 'note' | 'link',
      value: match[2],
    })
  }

  const cleanText = cellValue.replace(/\[(fx|note|link):[^\]]+\]/g, '').trim()

  return { cleanText, annotations }
}
