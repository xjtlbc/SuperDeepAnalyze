
interface SheetTabsProps {
  sheets: Array<{ name: string }>
  activeIndex: number
  onSelect: (index: number) => void
}

export function SheetTabs({ sheets, activeIndex, onSelect }: SheetTabsProps) {
  if (sheets.length <= 1) return null

  return (
    <div className="sheet-tabs">
      {sheets.map((sheet, i) => (
        <button
          key={i}
          className={`sheet-tab ${i === activeIndex ? 'active' : ''}`}
          onClick={() => onSelect(i)}
          title={sheet.name}
        >
          {sheet.name}
        </button>
      ))}
    </div>
  )
}
