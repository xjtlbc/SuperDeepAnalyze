"""Event types for agent loop display."""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class EventType(str, Enum):
    """Types of events emitted during agent execution."""
    THINKING = "thinking"           # Agent思考过程
    TOOL_CALL = "tool_call"         # 工具调用开始
    TOOL_RESULT = "tool_result"     # 工具调用结果
    RETRIEVAL_HIT = "retrieval_hit" # 检索命中信息
    DECISION = "decision"           # 决策点（如层级选择）
    ASK_USER = "ask_user"           # 请求用户输入
    FINAL_ANSWER = "final_answer"   # 最终答案
    ERROR = "error"                 # 错误信息


class AgentEvent(BaseModel):
    """Event emitted during agent execution loop."""
    type: EventType
    id: str                         # 事件唯一ID
    timestamp: float                # 时间戳
    content: Optional[str] = None   # 文本内容
    tool_name: Optional[str] = None # 工具名称
    tool_args: Optional[Dict[str, Any]] = None  # 工具参数
    tool_result: Optional[Any] = None  # 工具返回结果
    level: Optional[str] = None     # 检索层级 (L0/L1/L2)
    relevance_score: Optional[float] = None  # 相关性评分
    confidence: Optional[str] = None  # 置信度标签
    drill_path: Optional[List[str]] = None  # 钻探路径
    duration_ms: Optional[int] = None  # 耗时