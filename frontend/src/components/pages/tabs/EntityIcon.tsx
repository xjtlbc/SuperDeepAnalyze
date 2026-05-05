import { PersonIcon, FolderIcon, ClockIcon, DatabaseIcon, InfoIcon, FileTextIcon, ExternalLinkIcon, AlertCircleIcon, GraphIcon } from '../../Icons'

function MapPinIcon({ className }: { className?: string }) {
  return (
    <svg className={className || 'icon-sm'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  )
}

export function EntityTypeIcon({ type, className = 'icon-sm' }: { type: string; className?: string }) {
  switch (type) {
    case 'person': return <PersonIcon className={className} />
    case 'location': return <MapPinIcon className={className} />
    case 'organization': return <DatabaseIcon className={className} />
    case 'event': return <ClockIcon className={className} />
    case 'object': return <FolderIcon className={className} />
    case 'concept': return <InfoIcon className={className} />
    default: return <FileTextIcon className={className} />
  }
}

export function GapIconRenderer({ type, className = 'icon-sm' }: { type: string; className?: string }) {
  switch (type) {
    case 'isolated_entity': return <ExternalLinkIcon className={className} />
    case 'missing_relation': return <AlertCircleIcon className={className} />
    case 'unanswered_question': return <InfoIcon className={className} />
    case 'sparse_community': return <GraphIcon className={className} />
    default: return <AlertCircleIcon className={className} />
  }
}
