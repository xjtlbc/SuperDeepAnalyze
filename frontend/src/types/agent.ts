export interface AgentEvent {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'retrieval_hit' | 'decision' | 'ask_user' | 'final_answer' | 'error' | 'intent_analysis' | 'reflection' | 'turn_summary' | 'phase' | 'progress' | 'context_update'
  id: string
  timestamp: number
  content?: string
  tool_name?: string
  tool_args?: Record<string, unknown>
  tool_result?: string | Record<string, unknown> | null
  level?: 'L0' | 'L1' | 'L2'
  relevance_score?: number
  confidence?: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS'
  drill_path?: string[]
  duration_ms?: number
  // Intent analysis fields
  question_type?: string
  complexity?: string
  sub_queries?: { query: string; layer: string; priority: number }[]
  // Reflection fields
  answered_aspects?: string[]
  missing_aspects?: string[]
  evidence_strength?: string
  // Phase / progress
  phase?: string
  // Context update
  token_usage?: number
  token_limit?: number
  action?: string
}