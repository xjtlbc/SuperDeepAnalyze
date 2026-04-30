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
    <div className="ask-user-block border-2 border-amber-400 dark:border-amber-500 rounded-xl p-4 bg-amber-50/50 dark:bg-amber-900/10 my-2">
      <div className="flex items-center gap-2 mb-3">
        <svg className="w-4 h-4 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="text-sm font-medium text-amber-700 dark:text-amber-300">
          Agent 需要你的确认
        </span>
      </div>

      <p className="text-sm text-stone-700 dark:text-stone-300 mb-3 leading-relaxed">
        {event.content || event.tool_args?.question as string || '请选择或输入你的回答'}
      </p>

      {options.length > 0 && (
        <div className="space-y-2 mb-3">
          {options.map((opt, i) => (
            <button
              key={i}
              onClick={() => onReply(opt)}
              disabled={disabled}
              className="block w-full text-left px-3 py-2 rounded-lg border border-amber-300 dark:border-amber-600 hover:bg-amber-100 dark:hover:bg-amber-900/30 text-sm text-stone-700 dark:text-stone-300 transition-colors disabled:opacity-50"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-2">
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
          className="flex-1 px-3 py-2 rounded-lg border border-stone-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-50"
        />
        <button
          onClick={() => {
            if (freeText.trim()) {
              onReply(freeText.trim())
              setFreeText('')
            }
          }}
          disabled={disabled || !freeText.trim()}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
        >
          回复
        </button>
      </div>
    </div>
  )
}
