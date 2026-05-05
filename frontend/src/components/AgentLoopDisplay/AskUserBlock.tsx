import { useState } from 'react'
import type { AgentEvent } from '../../types/agent'

interface AskUserBlockProps {
  event: AgentEvent
  onReply: (answer: string) => void
  disabled?: boolean
}

export function AskUserBlock({ event, onReply, disabled }: AskUserBlockProps) {
  const [freeText, setFreeText] = useState('')
  const options: string[] = Array.isArray(event.tool_args?.options)
    ? (event.tool_args.options as string[])
    : []

  return (
    <div className="ask-user">
      <div className="ask-user__header">
        <svg className="ask-user__icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="ask-user__title">Agent 需要你的确认</span>
      </div>

      <p className="ask-user__question">
        {event.content || event.tool_args?.question as string || '请选择或输入你的回答'}
      </p>

      {options.length > 0 && (
        <div className="ask-user__options">
          {options.map((opt, i) => (
            <button
              key={i}
              onClick={() => onReply(opt)}
              disabled={disabled}
              className="ask-user__option-btn"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <div className="ask-user__input-row">
        <input
          type="text"
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && freeText.trim() && !disabled) {
              onReply(freeText.trim())
              setFreeText('')
            }
          }}
          placeholder="或输入自定义回答..."
          disabled={disabled}
          className="ask-user__input"
        />
        <button
          onClick={() => {
            if (freeText.trim()) {
              onReply(freeText.trim())
              setFreeText('')
            }
          }}
          disabled={disabled || !freeText.trim()}
          className="ask-user__reply-btn"
        >
          回复
        </button>
      </div>
    </div>
  )
}
