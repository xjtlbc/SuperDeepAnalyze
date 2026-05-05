export interface WorkflowStepInfo {
  step_id: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  duration?: number
  entity_count?: number
  result_preview?: string
}

export interface AgentEvent {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'retrieval_hit' | 'decision' | 'ask_user' | 'final_answer' | 'error' | 'intent_analysis' | 'reflection' | 'turn_summary' | 'phase' | 'progress' | 'context_update' | 'workflow_result'
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
  // Workflow fields
  workflow_mode?: 'pipeline' | 'parallel' | 'verify'
  workflow_steps?: WorkflowStepInfo[]
  workflow_synthesis?: string
  workflow_total_entities?: number
  workflow_total_duration?: number
}