import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface WikiPageProps {
  content: string
  frontmatter?: Record<string, any>
  className?: string
  onWikilinkClick?: (target: string) => void
  onSourceClick?: (docId: string) => void
}

export const WikiPageRenderer: React.FC<WikiPageProps> = ({ content, frontmatter, className, onWikilinkClick }) => {
  const renderWikilink = (target: string, display: string) => {
    return (
      <a
        href="#"
        className="wikilink text-amber-500 hover:text-amber-400 underline decoration-amber-500/30 hover:decoration-amber-400/50"
        onClick={(e) => {
          e.preventDefault()
          onWikilinkClick?.(target)
        }}
      >
        {display}
      </a>
    )
  }

  return (
    <div className={`wiki-page ${className || ''}`}>
      {frontmatter && (
        <div className="wiki-page-header mb-4 pb-4 border-b border-gray-700">
          <h1 className="text-2xl font-bold text-gray-100">{frontmatter.title}</h1>
          {frontmatter.tags && frontmatter.tags.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {frontmatter.tags.map((tag: string, i: number) => (
                <span key={i} className="px-2 py-0.5 text-xs bg-amber-100/10 dark:bg-amber-900/30 text-amber-600 dark:text-amber-300 rounded-full">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="wiki-page-content prose prose-sm prose-invert max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children, ...props }) => {
              // Process wikilinks in paragraph text
              const text = React.Children.toArray(children).join('')
              if (text.includes('[[') && text.includes(']]')) {
                const parts = text.split(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g)
                const elements: React.ReactNode[] = []
                for (let i = 0; i < parts.length; i++) {
                  if (i % 4 === 1) {
                    // target
                    const display = parts[i + 1] || parts[i]
                    elements.push(renderWikilink(parts[i], display))
                    i++ // skip display since we handled it
                  } else if (i % 4 !== 2) {
                    elements.push(parts[i])
                  }
                }
                return <p {...props}>{elements}</p>
              }
              return <p {...props}>{children}</p>
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
