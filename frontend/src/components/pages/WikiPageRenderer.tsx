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
        className="wiki-page__wikilink"
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
        <div className="wiki-page__header">
          <h1 className="wiki-page__header-title">{frontmatter.title}</h1>
          {frontmatter.tags && frontmatter.tags.length > 0 && (
            <div className="wiki-page__tags">
              {frontmatter.tags.map((tag: string, i: number) => (
                <span key={i} className="wiki-page__tag">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="wiki-page__content">
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
